from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import patch
from pathlib import Path
from tempfile import TemporaryDirectory
import sqlite3

from PIL import Image, ImageDraw

from pixel_ops.data_sources.ai_activity import AIActivitySnapshot, AIActivityTask
from pixel_ops.data_sources.codex_status import CodexStatusSource, activity_snapshot, thread_activity
from pixel_ops.events.observation_sources import ObservationEventSource
from pixel_ops.plugins.pokemon.game.day_night import day_night_palette
from pixel_ops.render.hud import draw_codex_status_panel


class CodexStatusTests(TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)

    def test_lifecycle_and_attention(self):
        self.assertEqual(thread_activity({'type': 'active'}), ('processing', 'running'))
        self.assertEqual(thread_activity({'type': 'active', 'activeFlags': ['waitingOnApproval']}), ('attention', 'approval'))
        self.assertEqual(thread_activity({'type': 'active', 'activeFlags': ['waitingOnUserInput']}), ('attention', 'input'))
        self.assertEqual(thread_activity({'type': 'idle'}, 'completed'), ('ready', 'completed'))
        for status in ('failed', 'interrupted'):
            self.assertEqual(thread_activity({'type': 'idle'}, status)[0], 'attention')
        self.assertEqual(thread_activity({'type': 'systemError'})[0], 'attention')
        self.assertEqual(thread_activity({'type': 'notLoaded'})[0], 'unknown')
        self.assertEqual(thread_activity({'type': 'idle'})[0], 'unknown')

    def test_multiple_sessions_prioritize_attention_and_never_fake_completion(self):
        snapshot = activity_snapshot([('ready', 'completed'), ('processing', 'running'), ('attention', 'input')], self.now)
        self.assertEqual((snapshot.state, snapshot.processing, snapshot.attention, snapshot.ready), ('attention', 1, 1, 1))
        self.assertEqual(activity_snapshot([], self.now).state, 'unknown')
        self.assertEqual(activity_snapshot([('unknown', 'no_session'), ('ready', 'completed')], self.now).state, 'unknown')

    def test_running_work_clears_historical_interruptions_but_not_live_requests(self):
        for reason in ('interrupted', 'error'):
            self.assertEqual(activity_snapshot([('attention', reason), ('processing', 'running')], self.now).state, 'processing')
        for reason in ('approval', 'input', 'system_error'):
            self.assertEqual(activity_snapshot([('processing', 'running'), ('attention', reason)], self.now).reason, reason)

    @patch('websocket.create_connection')
    @patch('pixel_ops.data_sources.codex_status.socket.socket')
    def test_read_only_protocol_pagination_and_turn_status(self, raw_socket, connect):
        import json
        connection = connect.return_value
        responses = iter([
            {}, {'data': ['child'], 'nextCursor': 'page2'}, {'data': ['temporary', 'root'], 'nextCursor': None},
            {'thread': {'source': {'subAgent': {}}, 'status': {'type': 'active'}}},
            {'thread': {'source': 'vscode', 'ephemeral': True, 'status': {'type': 'idle'}}},
            {'thread': {'source': 'vscode', 'status': {'type': 'idle'}}},
            {'data': [{'status': 'interrupted'}]},
        ])
        pending = []
        def send(raw):
            request = json.loads(raw)
            if 'id' in request:
                pending.append(json.dumps({'id': request['id'], 'result': next(responses)}))
        connection.send.side_effect = send
        connection.recv.side_effect = lambda: pending.pop(0)
        source = CodexStatusSource(socket_path='/test/daemon.sock')
        event = ObservationEventSource('ai.activity_updated', 'codex_status', source).poll(self.now)[0]
        self.assertEqual(event.payload['value'].reason, 'interrupted')
        requests = [json.loads(args.args[0]) for args in connection.send.call_args_list]
        self.assertEqual({r['method'] for r in requests}, {'initialize', 'initialized', 'thread/loaded/list', 'thread/read', 'thread/turns/list'})
        self.assertEqual(requests[-1]['params']['itemsView'], 'notLoaded')
        connection.close.assert_called_once()
        raw_socket.return_value.close.assert_called_once()

    @patch('pixel_ops.data_sources.codex_status.socket.socket')
    def test_disconnect_emits_unknown(self, raw_socket):
        raw_socket.return_value.connect.side_effect = OSError('offline')
        self.assertEqual(CodexStatusSource(socket_path='/test/daemon.sock').current(self.now).state, 'unknown')

    @patch('pixel_ops.data_sources.codex_status.socket.socket')
    def test_desktop_turns_override_unrelated_completed_daemon(self, raw_socket):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'ipc').mkdir()
            (root / 'ipc/ipc.sock').touch()
            metadata = sqlite3.connect(root / 'state_5.sqlite')
            metadata.execute('CREATE TABLE threads (id TEXT, source TEXT, archived INTEGER, updated_at INTEGER)')
            metadata.executemany('INSERT INTO threads VALUES (?, ?, ?, ?)', [
                ('desktop', 'vscode', 0, self.now.timestamp()),
                ('child', '{"subAgent": {}}', 0, self.now.timestamp()),
                ('archived', 'vscode', 1, self.now.timestamp()),
                ('old', 'vscode', 0, self.now.timestamp() - 1801),
                ('previous', 'vscode', 0, self.now.timestamp() - 60),
            ])
            metadata.commit()
            metadata.close()
            history = sqlite3.connect(root / 'thread_history_1.sqlite')
            history.execute('CREATE TABLE thread_turns (thread_id TEXT, rollout_ordinal INTEGER, status TEXT)')
            history.executemany('INSERT INTO thread_turns VALUES (?, ?, ?)', [
                ('desktop', 1, 'completed'), ('desktop', 2, 'inProgress'),
                ('child', 1, 'failed'), ('archived', 1, 'failed'), ('old', 1, 'interrupted'),
                ('previous', 1, 'interrupted'),
            ])
            history.commit()
            source = CodexStatusSource()
            source.codex_dir = root
            with patch.object(source, '_server_states', return_value={'daemon': ('ready', 'completed')}):
                snapshot = source.current(self.now)
                self.assertEqual((snapshot.state, snapshot.processing, snapshot.ready), ('processing', 1, 0))
                self.assertEqual(snapshot.tasks, (AIActivityTask('desktop', 'processing', 'running'),))
                history.execute("UPDATE thread_turns SET status = 'completed' WHERE rollout_ordinal = 2")
                history.commit()
                self.assertEqual(source.current(self.now).state, 'ready')
                history.execute("INSERT INTO thread_turns VALUES ('desktop', 3, 'inProgress')")
                history.commit()
                self.assertEqual(source.current(self.now).state, 'processing')
                history.execute("UPDATE thread_turns SET status = 'interrupted' WHERE rollout_ordinal = 3")
                history.commit()
                self.assertEqual(source.current(self.now).reason, 'interrupted')
                history.execute("INSERT INTO thread_turns VALUES ('desktop', 4, 'inProgress')")
                history.commit()
                self.assertEqual(source.current(self.now).state, 'processing')
            source.thread_id = 'desktop'
            self.assertEqual(source._desktop_states(self.now), {'desktop': ('processing', 'running')})
            source.thread_id = 'missing'
            self.assertEqual(source._desktop_states(self.now), {})
            history.close()

    def test_old_daemon_failures_do_not_replace_new_desktop_completion(self):
        source = CodexStatusSource()
        with patch.object(source, '_desktop_states', return_value={'new': ('ready', 'completed')}):
            for reason in ('interrupted', 'error'):
                with patch.object(source, '_server_states', return_value={'old': ('attention', reason)}):
                    self.assertEqual(source.current(self.now).state, 'ready')

    def test_missing_desktop_state_cannot_report_daemon_completion(self):
        source = CodexStatusSource()
        with patch.object(source, '_desktop_states', side_effect=sqlite3.OperationalError('unavailable')):
            with patch.object(source, '_server_states', return_value={'daemon': ('ready', 'completed')}):
                self.assertEqual(source.current(self.now).state, 'unknown')

    def test_duplicate_sessions_and_live_approval_take_priority(self):
        source = CodexStatusSource()
        with patch.object(source, '_desktop_states', return_value={'root': ('processing', 'running')}):
            with patch.object(source, '_server_states', return_value={'root': ('ready', 'completed')}):
                snapshot = source.current(self.now)
                self.assertEqual((snapshot.state, snapshot.processing, snapshot.ready), ('processing', 1, 0))
            with patch.object(source, '_server_states', return_value={'root': ('attention', 'approval')}):
                self.assertEqual(source.current(self.now).reason, 'approval')
            with patch.object(source, '_server_states', return_value=None):
                self.assertEqual(source.current(self.now).state, 'processing')

    def test_render_colors_clipping_and_stale_snapshot(self):
        colors = {'attention': (239, 83, 80), 'processing': (247, 201, 72), 'ready': (82, 198, 120)}
        for state, color in colors.items():
            image = Image.new('RGB', (240, 90), (1, 2, 3))
            snapshot = AIActivitySnapshot('codex', state, 'completed', self.now)
            draw_codex_status_panel(ImageDraw.Draw(image), snapshot, self.now, (10, 10, 230, 80), day_night_palette(12))
            self.assertIn(color, image.getdata())
            self.assertEqual(image.getpixel((9, 20)), (1, 2, 3))
        image = Image.new('RGB', (220, 70))
        stale = AIActivitySnapshot('codex', 'ready', 'completed', self.now - timedelta(seconds=16))
        draw_codex_status_panel(ImageDraw.Draw(image), stale, self.now, (0, 0, 220, 70), day_night_palette(12))
        self.assertNotIn(colors['ready'], image.getdata())
        for size in ((1, 1), (20, 10), (80, 32)):
            image = Image.new('RGB', size)
            draw_codex_status_panel(ImageDraw.Draw(image), None, self.now, (0, 0, *size), day_night_palette(12))

    def test_each_task_has_its_own_dot_and_stale_data_clears_them(self):
        snapshot = AIActivitySnapshot('codex', 'attention', 'input', self.now, tasks=(
            AIActivityTask('task-0001', 'processing', 'running'),
            AIActivityTask('task-0002', 'attention', 'input'),
        ))
        image = Image.new('RGB', (240, 72))
        draw_codex_status_panel(ImageDraw.Draw(image), snapshot, self.now, (0, 0, 240, 72), day_night_palette(12))
        left = set(image.crop((4, 14, 50, 66)).getdata())
        right = set(image.crop((50, 14, 96, 66)).getdata())
        self.assertIn((247, 201, 72), left)
        self.assertNotIn((239, 83, 80), left)
        self.assertIn((239, 83, 80), right)
        stale_image = Image.new('RGB', (240, 72))
        draw_codex_status_panel(ImageDraw.Draw(stale_image), snapshot, self.now + timedelta(seconds=16), (0, 0, 240, 72), day_night_palette(12))
        self.assertNotIn((247, 201, 72), stale_image.getdata())
        self.assertNotIn((239, 83, 80), stale_image.getdata())

    def test_narrow_hud_pages_through_tasks(self):
        snapshot = AIActivitySnapshot('codex', 'attention', 'input', self.now, tasks=(
            AIActivityTask('one', 'processing', 'running'),
            AIActivityTask('two', 'attention', 'input'),
        ))
        pages = []
        for offset in (0, 4):
            image = Image.new('RGB', (40, 40))
            draw_codex_status_panel(ImageDraw.Draw(image), snapshot, self.now + timedelta(seconds=offset), (0, 0, 40, 40), day_night_palette(12))
            pages.append(set(image.getdata()))
        self.assertTrue(any((247, 201, 72) in pixels for pixels in pages))
        self.assertTrue(any((239, 83, 80) in pixels for pixels in pages))
