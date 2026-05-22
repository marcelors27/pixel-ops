import { useState } from "react";

type PixelMascotProps = {
  src: string;
  sleepySrc: string;
  alertSrc: string;
};

export function PixelMascot({ src, sleepySrc, alertSrc }: PixelMascotProps) {
  const [mood, setMood] = useState<"idle" | "sleepy" | "alert">("idle");
  const image = mood === "sleepy" ? sleepySrc : mood === "alert" ? alertSrc : src;

  return (
    <button
      className="mascot-button"
      type="button"
      onClick={() => setMood((current) => (current === "idle" ? "sleepy" : current === "sleepy" ? "alert" : "idle"))}
      aria-label="Cycle mascot mood"
    >
      <img src={image} alt="Pixel OPs companion mascot" />
    </button>
  );
}
