"use client";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { CodeListPanel } from "@/components/admin/code-list-panel";
import { LLMConnectivityPanel } from "@/components/admin/llm-connectivity-panel";
import { RulesPanel } from "@/components/admin/rules-panel";
import { ThresholdPanel } from "@/components/admin/threshold-panel";

// Users/roles was originally planned for this page too (PROMPTS.md's 4.6 spec) -
// dropped 2026-10-14 per CLAUDE.md's decision log: RBAC/login is out of scope
// for now (disabled via AUTH_DISABLED, not deleted), so there's no active
// enforcement for a users/roles screen to manage.
export default function AdminPage() {
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">Admin</h1>
      <Tabs defaultValue="codes">
        <TabsList>
          <TabsTrigger value="codes">Code lists</TabsTrigger>
          <TabsTrigger value="rules">Rules</TabsTrigger>
          <TabsTrigger value="threshold">Threshold</TabsTrigger>
          <TabsTrigger value="llm">LLM Connectivity</TabsTrigger>
        </TabsList>
        <TabsContent value="codes" className="pt-4">
          <CodeListPanel />
        </TabsContent>
        <TabsContent value="rules" className="pt-4">
          <RulesPanel />
        </TabsContent>
        <TabsContent value="threshold" className="pt-4">
          <ThresholdPanel />
        </TabsContent>
        <TabsContent value="llm" className="pt-4">
          <LLMConnectivityPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}
