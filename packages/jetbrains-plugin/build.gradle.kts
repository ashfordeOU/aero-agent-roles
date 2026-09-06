import org.jetbrains.intellij.platform.gradle.TestFrameworkType

plugins {
    id("java")
    id("org.jetbrains.kotlin.jvm") version "2.0.21"
    id("org.jetbrains.intellij.platform") version "2.1.0"
}

group = "com.ashforde.aeroroles"
version = "1.1.0"

repositories {
    mavenCentral()
    intellijPlatform {
        defaultRepositories()
    }
}

kotlin {
    jvmToolchain(21)
}

dependencies {
    intellijPlatform {
        // Supports IntelliJ IDEA, WebStorm, PyCharm, and all other JetBrains IDEs
        intellijIdeaCommunity("2024.2")
        pluginVerifier()
        zipSigner()
        instrumentationTools()
        testFramework(TestFrameworkType.Platform)
    }
    testImplementation("org.junit.jupiter:junit-jupiter:5.10.0")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

intellijPlatform {
    projectName = "aero-agent-roles"

    pluginConfiguration {
        id = "com.ashforde.aeroroles"
        name = "Aero Agent Roles"
        version = project.version.toString()

        description = """
            <p><b>Aero Agent Roles</b> — the role layer for aerospace engineering agents.</p>
            <p>A skill does one task correctly. A role binds the right verified skills from
            Aero Agent Skills into a certification workflow, in order, with evidence gates at
            every stage and a human sign-off line that is never crossed.</p>
            <ul>
                <li><b>22+ roles</b> across aerodynamics, avionics, flight mechanics,
                    GNC/autonomy, propulsion, structures, space systems, and more</li>
                <li><b>Role catalog browser</b> — search and inspect any role in the IDE</li>
                <li><b>One-click MCP registration</b> — connect JetBrains AI Assistant / Junie to
                    the role catalog server (<code>npx -y aero-agent-roles mcp</code>)</li>
                <li><b>External registry</b> — add the GitHub repo as a registry so the AI
                    Assistant can browse roles directly</li>
            </ul>
            <p>Open source, Apache-2.0. Repo: <a href="https://github.com/ashfordeOU/aero-agent-roles">github.com/ashfordeOU/aero-agent-roles</a>.
            Landing page: <a href="https://ashforde.org/aeroagentroles">ashforde.org/aeroagentroles</a>.</p>
        """.trimIndent()

        ideaVersion {
            sinceBuild = "242"
        }
    }

    signing {
        certificateChain = System.getenv("PLUGIN_CERTIFICATE_CHAIN")
        privateKey = System.getenv("PLUGIN_PRIVATE_KEY")
        password = System.getenv("PLUGIN_PRIVATE_KEY_PASSWORD")
    }

    publishing {
        token = System.getenv("PUBLISH_TOKEN")
        hidden = false
    }
}

tasks {
    test {
        useJUnitPlatform()
    }
}
