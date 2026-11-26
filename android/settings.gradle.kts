pluginManagement {
    repositories {
        google()
        gradlePluginPortal()
        mavenCentral()
        // Chaquopy: Python dentro do app Android (plugin oficial, MIT).
        maven { url = uri("https://chaquo.com/maven") }
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
        maven { url = uri("https://chaquo.com/maven") }
    }
}

rootProject.name = "TermometroEmocional"
include(":app")
