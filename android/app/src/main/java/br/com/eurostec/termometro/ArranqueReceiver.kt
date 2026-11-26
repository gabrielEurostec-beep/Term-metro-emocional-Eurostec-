package br.com.eurostec.termometro

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

/** Quando o tablet liga, abre o Termômetro sozinho (se ele não tiver sido fechado pela administração). */
class ArranqueReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            context.startActivity(
                Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            )
        }
    }
}
