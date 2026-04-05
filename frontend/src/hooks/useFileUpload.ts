"use client";

import { useCallback, useRef, useState } from "react";
import { api } from "@/lib/api";
import type { UploadResult } from "@/lib/types";
import { summarizeUpload, uploadWarnings } from "@/lib/upload";

export type FileStatus = "queued" | "uploading" | "done" | "error";

export interface FileEntry {
  id: string;
  file: File;
  status: FileStatus;
  summary: string | null;
  warnings: string[];
  error: string | null;
  result: UploadResult | null;
}

interface UseFileUploadOptions {
  manager?: string;
  onAllComplete?: () => void;
}

export function useFileUpload(options: UseFileUploadOptions = {}) {
  const [entries, setEntries] = useState<FileEntry[]>([]);
  const [processing, setProcessing] = useState(false);
  const processingRef = useRef(false);
  const optionsRef = useRef(options);
  optionsRef.current = options;

  const updateEntry = useCallback((id: string, patch: Partial<FileEntry>) => {
    setEntries((prev) => prev.map((e) => (e.id === id ? { ...e, ...patch } : e)));
  }, []);

  const processQueue = useCallback(async (queue: FileEntry[]) => {
    if (processingRef.current) return;
    processingRef.current = true;
    setProcessing(true);

    for (const entry of queue) {
      updateEntry(entry.id, { status: "uploading" });
      try {
        const result = await api.uploadDocument(entry.file, optionsRef.current.manager);
        updateEntry(entry.id, {
          status: "done",
          summary: summarizeUpload(result),
          warnings: uploadWarnings(result),
          result,
        });
      } catch (err) {
        updateEntry(entry.id, {
          status: "error",
          error: err instanceof Error ? err.message : "Upload failed",
        });
      }
    }

    processingRef.current = false;
    setProcessing(false);
    optionsRef.current.onAllComplete?.();
  }, [updateEntry]);

  const addFiles = useCallback((files: FileList | File[]) => {
    const newEntries: FileEntry[] = Array.from(files).map((file) => ({
      id: `${file.name}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      file,
      status: "queued" as const,
      summary: null,
      warnings: [],
      error: null,
      result: null,
    }));

    setEntries((prev) => [...prev, ...newEntries]);
    processQueue(newEntries);
  }, [processQueue]);

  const clear = useCallback(() => {
    if (!processingRef.current) {
      setEntries([]);
    }
  }, []);

  const hasResults = entries.length > 0;
  const doneCount = entries.filter((e) => e.status === "done").length;
  const errorCount = entries.filter((e) => e.status === "error").length;

  return { entries, addFiles, clear, processing, hasResults, doneCount, errorCount };
}
