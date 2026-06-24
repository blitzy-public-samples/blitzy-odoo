import { Component, onWillStart, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { user } from "@web/core/user";
import { ClaudeAssistantPanel } from "../panel/claude_assistant_panel";

export class ClaudeSystrayItem extends Component {
    static template = "claude_assistant.SystrayItem";
    static props = [];
    static components = { ClaudeAssistantPanel };

    setup() {
        this.isInternal = false;
        this.state = useState({ open: false });
        onWillStart(async () => {
            this.isInternal = await user.hasGroup("base.group_user");
        });
    }

    toggle() {
        this.state.open = !this.state.open;
    }
}

export const systrayItem = { Component: ClaudeSystrayItem };
registry
    .category("systray")
    .add("claude_assistant.systray", systrayItem, { sequence: 100 });
