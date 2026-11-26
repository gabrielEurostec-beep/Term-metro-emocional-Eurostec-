package br.com.eurostec.termometro

import android.app.Application
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/** Inicia o Python (Chaquopy) uma vez, quando o aplicativo abre. */
class TermometroApp : Application() {
    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
    }
}
