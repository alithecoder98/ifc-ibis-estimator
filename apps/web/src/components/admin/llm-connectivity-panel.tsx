"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { useLLMConnectivity } from "@/lib/admin/use-llm-connectivity";
import { useTestLLMConnectivity } from "@/lib/admin/use-test-llm-connectivity";
import { useUpdateLLMConnectivity } from "@/lib/admin/use-update-llm-connectivity";

// This repo is published without the author's own local Ollama instance -
// every clone needs its own connection configured here instead of only via
// apps/api/.env, since not everyone running this has shell access to the
// deployment. DB-backed (app/core/settings_store.py), same pattern as the
// auto-accept threshold next to it: a change applies to the next
// classification/embedding call, no restart needed.
export function LLMConnectivityPanel() {
  const { data, isLoading, isError, refetch } = useLLMConnectivity();
  const update = useUpdateLLMConnectivity();
  const test = useTestLLMConnectivity();

  const [baseUrl, setBaseUrl] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [llmModel, setLlmModel] = useState("");

  // Only seed the fields once the real values have loaded - an empty-string
  // default would otherwise flash before overwriting itself, same reasoning
  // as ThresholdPanel.
  useEffect(() => {
    if (data) {
      setBaseUrl(data.base_url);
      setEmbeddingModel(data.embedding_model);
      setLlmModel(data.llm_model);
    }
  }, [data]);

  function currentValues() {
    return {
      base_url: baseUrl,
      embedding_model: embeddingModel,
      llm_model: llmModel,
    };
  }

  function handleSave(event: FormEvent) {
    event.preventDefault();
    update.mutate(currentValues());
  }

  function handleTest() {
    test.mutate(currentValues());
  }

  if (isLoading) {
    return <Skeleton className="h-64 w-full max-w-md rounded-xl" />;
  }
  if (isError) {
    return (
      <ErrorState
        message="Couldn't load the LLM connection settings."
        onRetry={() => refetch()}
      />
    );
  }

  return (
    <Card className="max-w-md">
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-medium">LLM connectivity</h3>
          <p className="text-muted-foreground text-sm">
            The Ollama host serving embeddings (code-list/example-memory search)
            and classification. Each person running this app points it at their
            own instance - nothing here is shared or baked into the codebase.
          </p>
        </div>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="llm-base-url">Ollama base URL</Label>
            <Input
              id="llm-base-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="http://localhost:11434"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="llm-embedding-model">Embedding model</Label>
            <Input
              id="llm-embedding-model"
              value={embeddingModel}
              onChange={(event) => setEmbeddingModel(event.target.value)}
              placeholder="bge-m3"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="llm-model">Classification (LLM) model</Label>
            <Input
              id="llm-model"
              value={llmModel}
              onChange={(event) => setLlmModel(event.target.value)}
              placeholder="qwen2.5:7b-instruct"
            />
          </div>
          <div className="flex gap-2">
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving..." : "Save"}
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={handleTest}
              disabled={test.isPending}
            >
              {test.isPending ? "Testing..." : "Test connection"}
            </Button>
          </div>
        </form>
        {update.isError && (
          <p className="text-sm text-red-600" role="alert">
            Couldn&apos;t save - check the values and try again.
          </p>
        )}
        {update.isSuccess && (
          <p className="text-sm text-green-700 dark:text-green-500">Saved.</p>
        )}
        {test.data && (
          <div
            className={`text-sm ${test.data.ok ? "text-green-700 dark:text-green-500" : "text-red-600"}`}
            role="status"
          >
            <p>{test.data.message}</p>
            {(test.data.available_models?.length ?? 0) > 0 && (
              <p className="text-muted-foreground mt-1 text-xs">
                Models on that host: {test.data.available_models?.join(", ")}
              </p>
            )}
          </div>
        )}
        {test.isError && (
          <p className="text-sm text-red-600" role="alert">
            Couldn&apos;t run the test - try again.
          </p>
        )}
      </CardContent>
    </Card>
  );
}
