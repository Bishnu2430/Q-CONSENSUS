import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";

type PlaybackState = "idle" | "loading" | "playing" | "error";

/** Per-message TTS playback: synthesizes on first play and caches the
 * resulting audio URL by message id so replaying doesn't re-synthesize. */
export function useTTS() {
  const [activeMessageId, setActiveMessageId] = useState<string | null>(null);
  const [state, setState] = useState<PlaybackState>("idle");
  const cacheRef = useRef<Map<string, string>>(new Map());
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const stop = useCallback(() => {
    audioRef.current?.pause();
    audioRef.current = null;
    setActiveMessageId(null);
    setState("idle");
  }, []);

  const play = useCallback(
    async (messageId: string, agentId: string, text: string) => {
      if (activeMessageId === messageId && state === "playing") {
        stop();
        return;
      }

      audioRef.current?.pause();
      setActiveMessageId(messageId);
      setState("loading");

      try {
        let url = cacheRef.current.get(messageId);
        if (!url) {
          const blob = await api.synthesizeSpeech(agentId, text);
          url = URL.createObjectURL(blob);
          cacheRef.current.set(messageId, url);
        }

        const audio = new Audio(url);
        audioRef.current = audio;
        audio.onended = () => {
          setState("idle");
          setActiveMessageId(null);
        };
        audio.onerror = () => setState("error");
        await audio.play();
        setState("playing");
      } catch {
        setState("error");
      }
    },
    [activeMessageId, state, stop],
  );

  return {
    activeMessageId,
    state,
    play,
    stop,
    isPlaying: (messageId: string) => activeMessageId === messageId && state === "playing",
    isLoading: (messageId: string) => activeMessageId === messageId && state === "loading",
  };
}
