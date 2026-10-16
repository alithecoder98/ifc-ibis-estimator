"use client";

import { type FormEvent, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/shared/error-state";
import { useLLMConnectivity } from "@/lib/admin/use-llm-connectivity";
import { useTestLLMConnectivity } from "@/lib/admin/use-test-llm-connectivity";
import { useUpdateLLMConnectivity } from "@/lib/admin/use-update-llm-connectivity";

type Provider = "ollama" | "openai_compatible";

const PROVIDER_LABELS: Record<Provider, string> = {
  ollama: "Ollama (local)",
  openai_compatible: "OpenAI-compatible API",
};

const PROVIDER_DEFAULTS: Record<
  Provider,
  { baseUrl: string; embeddingModel: string; llmModel: string }
> = {
  ollama: {
    baseUrl: "http://localhost:11434",
    embeddingModel: "bge-m3",
    llmModel: "qwen2.5:7b-instruct",
  },
  openai_compatible: {
    baseUrl: "https://api.openai.com/v1",
    // Not an OpenAI model - their own embedding models default to 1536/3072
    // dimensions, not the 1024 this database's pgvector column is fixed at (see
    // the warning text below the field). bge-m3 is dimension-safe and commonly
    // served over an OpenAI-compatible endpoint too.
    embeddingModel: "bge-m3",
    llmModel: "gpt-4o-mini",
  },
};

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

  const [provider, setProvider] = useState<Provider>("ollama");
  const [baseUrl, setBaseUrl] = useState("");
  const [embeddingModel, setEmbeddingModel] = useState("");
  const [llmModel, setLlmModel] = useState("");
  // Always starts empty - the API never echoes a saved key back (see
  // LLMConnectivityOut.has_api_key). Left blank on save/test, the backend
  // falls back to whatever's already stored instead of treating it as "no key".
  const [apiKey, setApiKey] = useState("");

  // Only seed the fields once the real values have loaded - an empty-string
  // default would otherwise flash before overwriting itself, same reasoning
  // as ThresholdPanel.
  useEffect(() => {
    if (data) {
      setProvider(data.provider);
      setBaseUrl(data.base_url);
      setEmbeddingModel(data.embedding_model);
      setLlmModel(data.llm_model);
    }
  }, [data]);

  const isOpenAICompatible = provider === "openai_compatible";

  // Switching providers with the dropdown must not leave the other fields
  // holding the *previous* provider's values under a misleading placeholder -
  // confirmed live: switching to OpenAI-compatible kept showing
  // "http://localhost:11434"/"bge-m3" verbatim, which would have saved a
  // connection that's wrong for the provider it claims to be. Restores the
  // originally-loaded values when switching back to the saved provider,
  // rather than clearing a value the user hasn't actually touched.
  function handleProviderChange(next: Provider) {
    setProvider(next);
    setApiKey("");
    if (data && next === data.provider) {
      setBaseUrl(data.base_url);
      setEmbeddingModel(data.embedding_model);
      setLlmModel(data.llm_model);
    } else {
      const defaults = PROVIDER_DEFAULTS[next];
      setBaseUrl(defaults.baseUrl);
      setEmbeddingModel(defaults.embeddingModel);
      setLlmModel(defaults.llmModel);
    }
  }

  function currentValues() {
    return {
      provider,
      base_url: baseUrl,
      embedding_model: embeddingModel,
      llm_model: llmModel,
      // Omitted (not an empty string) when untouched, so the backend's "leave
      // the saved key alone" fallback actually triggers - see
      // app/routers/settings.py's update_llm_connectivity.
      ...(isOpenAICompatible && apiKey.trim() !== ""
        ? { api_key: apiKey }
        : {}),
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
            Where embeddings (code-list/example-memory search) and
            classification come from. Each person running this app points it at
            their own connection - nothing here is shared or baked into the
            codebase.
          </p>
        </div>
        <form onSubmit={handleSave} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="llm-provider">Provider</Label>
            <Select
              value={provider}
              onValueChange={(value) =>
                handleProviderChange((value as Provider) ?? "ollama")
              }
            >
              <SelectTrigger id="llm-provider">
                {/* Base UI's Select.Value shows the raw stored value unless
                    given a children render-prop (unlike Radix). */}
                <SelectValue placeholder="Provider">
                  {(value: Provider) => PROVIDER_LABELS[value]}
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="ollama">{PROVIDER_LABELS.ollama}</SelectItem>
                <SelectItem value="openai_compatible">
                  {PROVIDER_LABELS.openai_compatible}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="llm-base-url">
              {isOpenAICompatible ? "API base URL" : "Ollama base URL"}
            </Label>
            <Input
              id="llm-base-url"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={
                isOpenAICompatible
                  ? "https://api.openai.com/v1"
                  : "http://localhost:11434"
              }
            />
          </div>
          {isOpenAICompatible && (
            <div className="space-y-2">
              <Label htmlFor="llm-api-key">API key</Label>
              <Input
                id="llm-api-key"
                type="password"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                placeholder={
                  data?.has_api_key
                    ? "Saved - leave blank to keep it"
                    : "sk-..."
                }
                autoComplete="off"
              />
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="llm-embedding-model">Embedding model</Label>
            <Input
              id="llm-embedding-model"
              value={embeddingModel}
              onChange={(event) => setEmbeddingModel(event.target.value)}
              placeholder="bge-m3"
            />
            {isOpenAICompatible && (
              <p className="text-muted-foreground text-xs">
                Must produce 1024-dimensional vectors to match this
                database&apos;s embedding column - a mismatched model fails on
                the next save/search rather than silently corrupting data.
              </p>
            )}
          </div>
          <div className="space-y-2">
            <Label htmlFor="llm-model">Classification (LLM) model</Label>
            <Input
              id="llm-model"
              value={llmModel}
              onChange={(event) => setLlmModel(event.target.value)}
              placeholder={
                isOpenAICompatible ? "gpt-4o-mini" : "qwen2.5:7b-instruct"
              }
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
