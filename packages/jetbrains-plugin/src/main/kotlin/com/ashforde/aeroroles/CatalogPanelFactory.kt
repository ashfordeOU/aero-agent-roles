package com.ashforde.aeroroles

import javax.swing.JComponent

/** Bridge used by the tool-window factory. */
object CatalogPanelFactory {
    fun create(): JComponent = RoleCatalogPanel()
}
