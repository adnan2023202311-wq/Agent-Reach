import {
  chatSuggestions,
  agentSuggestions,
  recentChats,
  type ChatMode,
  type Message,
} from "@/features/chat/data";
import type { ChatService, SendMessageInput } from "@/services/types";

export const chatMockService: ChatService = {
  suggestions: (mode: ChatMode) => (mode === "agent" ? agentSuggestions : chatSuggestions),
  recent: async () => recentChats,
  recentSync: () => recentChats,
  sendMessage: async (input: SendMessageInput): Promise<Message> => ({
    id: crypto.randomUUID(),
    role: "assistant",
    content:
      input.mode === "agent"
        ? `Agent "${input.agentId ?? "default"}" acknowledged: ${input.content}`
        : `Mock reply from ${input.providerId}/${input.modelId}: ${input.content}`,
    createdAt: Date.now(),
  }),
};
