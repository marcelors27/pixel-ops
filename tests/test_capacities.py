from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from pixel_ops.data_sources.capacities import CapacitiesProjectSource
from pixel_ops.data_sources.projects import ProjectItem, ProjectSnapshot, project_radar, project_radar_scores


NOW = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


class CapacitiesProjectSourceTests(unittest.TestCase):
    @patch("pixel_ops.data_sources.capacities.requests.get")
    def test_discovers_portuguese_project_type_and_maps_properties(self, get: Mock):
        structures = {
            "structures": [
                {
                    "id": "project-structure",
                    "title": "Projeto",
                    "pluralName": "Projetos",
                    "propertyDefinitions": [
                        {"id": "title", "name": "Title"},
                        {"id": "state-id", "name": "Estado"},
                        {"id": "action-id", "name": "Próxima ação"},
                        {"id": "review-id", "name": "Revisitar em"},
                        {"id": "importance-id", "name": "Importância"},
                        {"id": "health-id", "name": "Saúde"},
                        {"id": "progress-id", "name": "Progresso"},
                        {"id": "phase-id", "name": "Fase atual"},
                    ],
                }
            ]
        }
        objects = {"results": [{"id": "p1", "structureId": "project-structure", "title": "Casa inteligente"}]}
        detail = {
                    "id": "p1",
                    "lastUpdatedAt": "2026-08-20T10:00:00Z",
                    "properties": {
                        "title": {"type": "title", "title": {"value": "Casa inteligente"}},
                        "state-id": {"type": "label", "label": [{"id": "active", "name": "Ativo"}]},
                        "action-id": {"type": "text", "text": {"value": "Comparar Zigbee e Thread"}},
                        "review-id": {"type": "date", "date": {"start": "2026-08-25T00:00:00Z"}},
                        "importance-id": {"type": "number", "number": {"value": 3}},
                        "health-id": {"type": "label", "label": [{"id": "track", "name": "No rumo"}]},
                        "progress-id": {"type": "number", "number": {"value": 65}},
                        "phase-id": {"type": "label", "label": [{"id": "execution", "name": "Execução"}]},
                    },
        }
        get.side_effect = [_response(structures), _response(objects), _response(detail)]
        source = CapacitiesProjectSource(poll_seconds=1)

        with patch.dict(os.environ, {"PIXEL_OPS_CAPACITIES_TOKEN": "cap-api-test"}):
            snapshot = source.current(NOW)

        self.assertIsNotNone(snapshot)
        project = snapshot.projects[0]
        self.assertEqual(project.title, "Casa inteligente")
        self.assertEqual(project.state, "Ativo")
        self.assertEqual(project.next_action, "Comparar Zigbee e Thread")
        self.assertEqual(project.importance, 3)
        self.assertEqual(project.health, "No rumo")
        self.assertEqual(project.progress, 65)
        self.assertEqual(project.phase, "Execução")
        self.assertEqual(get.call_args_list[1].kwargs["params"]["id"], "project-structure")
        self.assertEqual(get.call_args_list[2].kwargs["params"]["id"], "p1")

    @patch("pixel_ops.data_sources.capacities.requests.get")
    def test_missing_project_type_is_an_actionable_empty_snapshot(self, get: Mock):
        get.return_value = _response({"structures": []})
        source = CapacitiesProjectSource()
        with patch.dict(os.environ, {"PIXEL_OPS_CAPACITIES_TOKEN": "cap-api-test"}):
            snapshot = source.current(NOW)
        self.assertEqual(snapshot.status, "missing_project_type")
        self.assertEqual(snapshot.projects, ())


class ProjectRadarTests(unittest.TestCase):
    def test_selects_active_focus_and_overdue_resurfacing(self):
        focus = ProjectItem("capacities", "focus", "Pixel Ops", "active", next_action="Draw HUD", touched_at=NOW - timedelta(days=1), importance=3)
        stale = ProjectItem("capacities", "stale", "Casa inteligente", "incubating", review_at=NOW - timedelta(days=2), touched_at=NOW - timedelta(days=40))
        inbox = ProjectItem("capacities", "inbox", "Nova ideia", "inbox", touched_at=NOW)
        radar = project_radar(ProjectSnapshot((focus, stale, inbox), NOW), NOW)
        self.assertEqual(radar.focus, focus)
        self.assertEqual(radar.resurfacing, stale)
        self.assertEqual(radar.inbox_count, 1)
        self.assertEqual(radar.review_count, 1)

    def test_builds_objective_chart_scores_from_project_properties(self):
        project = ProjectItem(
            "capacities",
            "focus",
            "Pixel Ops",
            "active",
            next_action="Polish HUD",
            review_at=NOW + timedelta(days=2),
            importance=3,
            health="No rumo",
            progress=65,
            phase="Execução",
        )
        self.assertEqual(project_radar_scores(project, NOW), (100, 100, 65, 90, 100))


def _response(payload: object) -> Mock:
    response = Mock()
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


if __name__ == "__main__":
    unittest.main()
