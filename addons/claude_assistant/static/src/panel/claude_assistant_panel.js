import { Component, onPatched, onWillStart, useRef, useState } from "@odoo/owl";
import { rpc } from "@web/core/network/rpc";
import { browser } from "@web/core/browser/browser";
import { useService } from "@web/core/utils/hooks";

/**
 * ClaudeAssistantPanel
 *
 * Role-aware Claude chat panel (the 2nd of the addon's two UI surfaces; the
 * systray entry is the first and renders this component, passing a `close`
 * callback). Conversation state is EPHEMERAL: it lives only in OWL `useState`
 * and is NEVER persisted to the server or database.
 *
 * Runtime contract with addons/claude_assistant/controllers/main.py:
 *  - GET  /claude_assistant/status -> standard JSON-RPC envelope; use rpc().
 *  - POST /claude_assistant/chat   -> FLAT body + REAL HTTP status (the
 *    controller bypasses the JSON-RPC envelope via abort+make_json_response);
 *    rpc() cannot read it, so we MUST use a raw browser.fetch and branch on the
 *    HTTP status code ourselves.
 */
export class ClaudeAssistantPanel extends Component {
    static template = "claude_assistant.Panel";
    static props = {
        close: { type: Function, optional: true },
    };

    setup() {
        this.notification = useService("notification");
        this.messagesRef = useRef("messages");
        this.state = useState({
            apiKeyConfigured: false,
            odooVersion: "",
            userRoles: [],
            activeRole: null,
            activeMode: null,
            // conversations: dict keyed by "{roleId}:{modeId}" -> [{role, content}]
            conversations: {},
            pending: false,
            draft: "",
        });

        onWillStart(async () => {
            const status = await rpc("/claude_assistant/status");
            this.state.apiKeyConfigured = Boolean(status.api_key_configured);
            this.state.odooVersion = status.odoo_version || "";
            this.state.userRoles = status.user_roles || [];
            if (this.state.userRoles.length) {
                const firstRole = this.state.userRoles[0];
                this.state.activeRole = firstRole.id;
                this.state.activeMode = firstRole.modes.length ? firstRole.modes[0].id : null;
            }
        });

        // Keep the transcript pinned to the latest message after each render.
        onPatched(() => this._scrollToBottom());
    }

    // ----- derived state -----
    get currentRole() {
        return this.state.userRoles.find((role) => role.id === this.state.activeRole) || null;
    }

    get currentModes() {
        return this.currentRole ? this.currentRole.modes : [];
    }

    get conversationKey() {
        return `${this.state.activeRole}:${this.state.activeMode}`;
    }

    get currentMessages() {
        return this.state.conversations[this.conversationKey] || [];
    }

    // ----- UI handlers -----
    onClose() {
        if (this.props.close) {
            this.props.close();
        }
    }

    selectRole(roleId) {
        if (roleId === this.state.activeRole) {
            return;
        }
        this.state.activeRole = roleId;
        const role = this.state.userRoles.find((entry) => entry.id === roleId);
        // Switching role preserves each role's per-mode conversations and
        // activates that role's FIRST mode.
        this.state.activeMode = role && role.modes.length ? role.modes[0].id : null;
    }

    selectMode(modeId) {
        // Switching mode preserves each mode's conversation (kept by key).
        this.state.activeMode = modeId;
    }

    onInput(ev) {
        this.state.draft = ev.target.value;
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.send();
        }
    }

    _ensureConversation(key) {
        if (!this.state.conversations[key]) {
            this.state.conversations[key] = [];
        }
        return this.state.conversations[key];
    }

    _scrollToBottom() {
        const el = this.messagesRef.el;
        if (el) {
            el.scrollTop = el.scrollHeight;
        }
    }

    async send() {
        const content = (this.state.draft || "").trim();
        if (!content || this.state.pending || !this.state.activeMode) {
            return;
        }
        const conversation = this._ensureConversation(this.conversationKey);
        conversation.push({ role: "user", content });
        this.state.draft = "";
        this.state.pending = true;
        try {
            // RAW fetch (NOT rpc): /chat returns a flat body + real HTTP status.
            // The body must still be a JSON-RPC envelope because the route is
            // dispatched by the jsonrpc dispatcher (reads params from the envelope).
            const res = await browser.fetch("/claude_assistant/chat", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                    jsonrpc: "2.0",
                    method: "call",
                    params: { mode: this.state.activeMode, messages: conversation },
                    id: Date.now(),
                }),
            });
            const body = await res.json();
            if (res.ok) {
                conversation.push({ role: "assistant", content: body.response || "" });
            } else {
                this.notification.add(body.error || "Unexpected error", { type: "danger" });
            }
        } catch {
            this.notification.add("Could not reach the Claude assistant.", { type: "danger" });
        } finally {
            this.state.pending = false;
        }
    }
}
