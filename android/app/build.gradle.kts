plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("com.chaquo.python")
}

// Raiz do repositório (pasta acima de android/).
val raizDoProjeto = rootProject.projectDir.parentFile

android {
    namespace = "br.com.eurostec.termometro"
    compileSdk = 35

    defaultConfig {
        applicationId = "br.com.eurostec.termometro"
        // Android 10 ou mais novo: os CSVs são copiados para Download via MediaStore.
        minSdk = 29
        targetSdk = 35
        versionCode = 1
        versionName = "1.0.0"
        ndk {
            // Python 3.12 do Chaquopy só tem estas arquiteturas (tablets atuais são 64 bits).
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    // Assinatura de publicação: só é usada se as variáveis de ambiente abaixo existirem
    // (o GitHub Actions as configura a partir dos secrets). Sem elas, gera APK de teste.
    signingConfigs {
        create("publicacao") {
            System.getenv("TERMOMETRO_KEYSTORE")?.let { storeFile = file(it) }
            storePassword = System.getenv("TERMOMETRO_KEYSTORE_SENHA")
            keyAlias = System.getenv("TERMOMETRO_CHAVE_ALIAS")
            keyPassword = System.getenv("TERMOMETRO_CHAVE_SENHA")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            if (System.getenv("TERMOMETRO_KEYSTORE") != null) {
                signingConfig = signingConfigs.getByName("publicacao")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        buildConfig = true
    }
}

chaquopy {
    defaultConfig {
        version = "3.12"
    }
}

// As telas e o código Python ficam no repositório, em quiosque/ e assets/.
// Antes de cada build, copiamos para as pastas que o Android e o Chaquopy leem.
// Assim não existe uma segunda cópia editável do código.
val copiarPython by tasks.registering(Copy::class) {
    from(raizDoProjeto.resolve("quiosque")) {
        include("**/*.py")
    }
    into(file("src/main/python/quiosque"))
}

val copiarTelas by tasks.registering(Copy::class) {
    from(raizDoProjeto.resolve("quiosque/web")) {
        into("termometro/web")
    }
    from(raizDoProjeto.resolve("assets")) {
        into("termometro/assets")
    }
    into(file("src/main/assets"))
}

tasks.matching {
    it.name == "preBuild" || it.name.startsWith("merge") || it.name.startsWith("generate") ||
        it.name.startsWith("extract") || it.name.startsWith("chaquopy")
}.configureEach {
    dependsOn(copiarPython, copiarTelas)
}

dependencies {
    implementation("org.jetbrains.kotlin:kotlin-stdlib:1.9.24")
}
