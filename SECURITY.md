# Segurança

Use a ferramenta apenas com arquivos que você tem direito de processar e compartilhar com o cliente de IA escolhido. Nunca indexe segredos. O indexador e as ferramentas MCP leem fontes locais, mas trechos retornados por MCP podem ser enviados ao provedor que atende a conversa. Verifique as regras de privacidade desse serviço antes de conectar uma coleção.

O servidor MCP expõe operações de busca, leitura de trechos indexados e estado. Ele não oferece escrita via MCP, execução de comandos contidos nos documentos, acesso HTTP nem leitura arbitrária de caminhos. A indexação e as alterações são feitas pela CLI local.

O conteúdo de fontes deve ser tratado como dado não confiável. Uma nota ou PDF pode conter instruções maliciosas; não as execute só por aparecerem em um resultado. Os resultados podem estar incompletos ou desatualizados e precisam ser conferidos na fonte.

Para relatar uma vulnerabilidade, use os mecanismos privados de contato de segurança disponibilizados pelo mantenedor do repositório. Inclua versão afetada, passos mínimos de reprodução e impacto. Não publique dados pessoais, segredos ou conteúdo de coleções de terceiros. Se não houver um canal privado indicado, abra uma issue sem detalhes exploráveis e solicite um canal seguro.

Não há promessa de resposta ou prazo de correção. Não teste a ferramenta contra sistemas ou dados alheios sem autorização.
