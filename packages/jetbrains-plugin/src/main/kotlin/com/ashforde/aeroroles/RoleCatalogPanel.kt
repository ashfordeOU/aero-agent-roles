package com.ashforde.aeroroles

import com.intellij.ide.BrowserUtil
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBScrollPane
import com.intellij.util.ui.JBUI
import org.jetbrains.annotations.NonNls
import java.awt.BorderLayout
import java.awt.event.MouseAdapter
import java.awt.event.MouseEvent
import javax.swing.*
import javax.swing.event.DocumentEvent
import javax.swing.event.DocumentListener

/**
 * Role catalog browser.
 *
 * Ships a static catalog snapshot (roles + domains + deliverables) so the
 * IDE panel works offline. The live catalog lives in the public repo's
 * packages/aero-agent-roles/manifest.json (regenerated on every release);
 * this snapshot is refreshed by scripts/gen_jetbrains_catalog.py at build
 * time via the plugin bundle task. Double-click a row to open its full
 * ROLE.md on GitHub.
 */
class RoleCatalogPanel : JPanel(BorderLayout()) {

    private val model = DefaultListModel<RoleRow>()
    private val allRoles: List<RoleRow> = loadCatalog()

    private val list = JBList(model)

    init {
        list.cellRenderer = object : DefaultListCellRenderer() {
            override fun getListCellRendererComponent(
                list: JList<*>?,
                value: Any?,
                index: Int,
                isSelected: Boolean,
                cellHasFocus: Boolean
            ): java.awt.Component {
                val c = super.getListCellRendererComponent(list, value, index, isSelected, cellHasFocus)
                if (value is RoleRow) {
                    text = "<html><b>${value.title}</b> — ${value.shortDeliverable()} " +
                        "<font color='gray'>(${value.domain} · binds ${value.skillsBound})</font></html>"
                }
                return c
            }
        }
        list.addMouseListener(object : MouseAdapter() {
            override fun mouseClicked(e: MouseEvent) {
                if (e.clickCount == 2) {
                    val row = list.selectedValue as? RoleRow ?: return
                    if (row.slug.isNotEmpty()) {
                        BrowserUtil.browse(
                            "https://github.com/ashfordeOU/aero-agent-roles/blob/main/roles/${row.slug}/ROLE.md"
                        )
                    }
                }
            }
        })

        val search = JTextField()
        search.toolTipText = "Search aerospace roles (title, domain, or deliverable)"
        search.document.addDocumentListener(object : DocumentListener {
            override fun insertUpdate(e: DocumentEvent?) = filter(search.text)
            override fun removeUpdate(e: DocumentEvent?) = filter(search.text)
            override fun changedUpdate(e: DocumentEvent?) = filter(search.text)
        })

        filter("")

        val hint = JLabel(
            "<html><small>Double-click a role to open its ROLE.md on GitHub. Install: " +
                "<b>Settings | Tools | AI Assistant</b> → Manage External Registries → add " +
                "<code>https://github.com/ashfordeOU/aero-agent-roles</code>. " +
                "Or connect MCP: Tools → <b>Copy MCP Server Config</b>.</small></html>"
        )
        hint.border = JBUI.Borders.empty(6)

        add(search, BorderLayout.NORTH)
        add(JBScrollPane(list), BorderLayout.CENTER)
        add(hint, BorderLayout.SOUTH)
    }

    private fun filter(query: String) {
        model.clear()
        val q = query.trim().lowercase()
        allRoles
            .filter {
                q.isEmpty() || it.title.lowercase().contains(q) ||
                    it.domain.lowercase().contains(q) || it.deliverable.lowercase().contains(q)
            }
            .take(500)
            .forEach { model.addElement(it) }
        if (model.isEmpty()) {
            model.addElement(RoleRow("", "(no roles match)", "", "", 0))
        }
    }

    private companion object {
        @NonNls
        private const val CATALOG_RESOURCE = "/catalog/catalog.json"

        fun loadCatalog(): List<RoleRow> {
            val stream = RoleCatalogPanel::class.java.getResourceAsStream(CATALOG_RESOURCE)
                ?: return listOf(RoleRow("", "(catalog not bundled)", "Build bundle task to embed catalog.json", "", 0))
            return try {
                val text = stream.bufferedReader().use { it.readText() }
                parseCatalog(text)
            } catch (e: Exception) {
                listOf(RoleRow("", "(catalog error: ${e.message})", "", "", 0))
            }
        }

        fun parseCatalog(json: String): List<RoleRow> {
            // Minimal JSON parse without external deps:
            // {"roles": [{slug, title, domain, deliverable_type, skills_bound}]}
            val rows = ArrayList<RoleRow>()
            val slugRe = Regex("\"slug\"\\s*:\\s*\"([^\"]*)\"")
            val titleRe = Regex("\"title\"\\s*:\\s*\"([^\"]*)\"")
            val domainRe = Regex("\"domain\"\\s*:\\s*\"([^\"]*)\"")
            val deliverableRe = Regex("\"deliverable_type\"\\s*:\\s*\"([^\"]*)\"")
            val boundRe = Regex("\"skills_bound\"\\s*:\\s*(\\d+)")
            val itemRe = Regex("\\{([^{}]*)}")
            for (m in itemRe.findAll(json)) {
                val block = m.groupValues[1]
                val slug = slugRe.find(block)?.groupValues?.get(1) ?: continue
                val title = titleRe.find(block)?.groupValues?.get(1) ?: slug
                val domain = domainRe.find(block)?.groupValues?.get(1) ?: ""
                val deliverable = deliverableRe.find(block)?.groupValues?.get(1) ?: ""
                val bound = boundRe.find(block)?.groupValues?.get(1)?.toIntOrNull() ?: 0
                rows.add(RoleRow(slug, title, domain, deliverable, bound))
            }
            return rows
        }
    }
}

/** Lightweight catalog row. */
data class RoleRow(
    val slug: String,
    val title: String,
    val domain: String,
    val deliverable: String,
    val skillsBound: Int
) {
    fun shortDeliverable(): String =
        if (deliverable.length > 70) deliverable.take(70) + "…" else deliverable
}
