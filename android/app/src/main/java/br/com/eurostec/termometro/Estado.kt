package br.com.eurostec.termometro

/** Situação compartilhada entre o serviço (que sobe o servidor) e a tela. */
object Estado {
    const val PORTA = 8080
    const val ENDERECO = "http://127.0.0.1:$PORTA"

    @Volatile var servidorIniciado = false
    @Volatile var erro: String? = null
}
