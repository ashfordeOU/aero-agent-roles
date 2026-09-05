package com.ashforde.aeroroles

import com.intellij.ide.BrowserUtil
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.ide.CopyPasteManager
import java.awt.datatransfer.StringSelection

/** Copies the MCP registration JSON for JetBrains AI Assistant / Junie. */
class CopyMcpConfigAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val json = """
            {
              "servers": {
                "aero-agent-roles": {
                  "type": "stdio",
                  "command": "npx",
                  "args": ["-y", "aero-agent-roles", "mcp"]
                }
              }
            }
        """.trimIndent()
        CopyPasteManager.getInstance().setContents(StringSelection(json))
        com.intellij.openapi.ui.Messages.showInfoMessage(
            e.project,
            "MCP config copied.\n\nPaste it in:\nSettings | Tools | AI Assistant | Model Context Protocol (MCP) | Add\n(or Junie MCP Settings).\n\nRequires Node.js (npx) on PATH.",
            "Aero Agent Roles — MCP config"
        )
    }
}

/** Copies the Aero Agent Roles external-registry URL for the AI Assistant. */
class CopyRegistryUrlAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        val url = "https://github.com/ashfordeOU/aero-agent-roles"
        CopyPasteManager.getInstance().setContents(StringSelection(url))
        com.intellij.openapi.ui.Messages.showInfoMessage(
            e.project,
            "Registry URL copied.\n\nAdd it in:\nSettings | Tools | AI Assistant\n→ Manage External Registries → Add\n\nAll roles become browsable in the AI Assistant.",
            "Aero Agent Roles — registry"
        )
    }
}

/** Opens the public landing page in the browser. */
class OpenDocsAction : AnAction() {
    override fun actionPerformed(e: AnActionEvent) {
        BrowserUtil.browse("https://ashforde.org/aeroagentroles")
    }
}
