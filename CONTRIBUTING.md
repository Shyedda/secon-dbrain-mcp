# Contribuir

Contribuições são bem-vindas para melhorar a documentação, compatibilidade, recuperação, acessibilidade e segurança da ferramenta.

## Fluxo

1. Abra uma issue para descrever mudanças maiores ou bugs difíceis de reproduzir.
2. Crie uma branch a partir da versão atual e mantenha a mudança focada.
3. Preserve os dados da coleção local: não inclua PDFs, notas de exemplo pessoais, índices, extrações, modelos ou credenciais no patch.
4. Faça as verificações pertinentes à área alterada e descreva o ambiente e os resultados no pull request.
5. Abra um pull request com problema, comportamento esperado, solução e limitações.

Não inclua chaves, tokens, arquivos `.env`, caminhos de usuário, conteúdo de documentos privados ou saídas que revelem dados da coleção. Use exemplos sintéticos que o próprio leitor execute com seus arquivos.

## Mudanças no indexador

Alterações em extração, segmentação, identidade de fontes, atualização incremental, exclusão ou publicação do índice precisam demonstrar que mudanças parciais não corrompem o estado e não regravam fontes. Cubra falhas antes da publicação, arquivos adicionados/alterados/removidos e consistência entre índice e origem, conforme aplicável.

Mudanças em esquemas devem manter os padrões genéricos funcionais e permitir a personalização local de áreas, filtros e padrões pelo usuário. Não copie configurações de uma biblioteca pessoal para o pacote público. Documente compatibilidade, migração de configuração e qualquer mudança que exija reconstrução explícita. Não altere silenciosamente a modalidade ou o modelo de uma coleção existente.

## Documentação

Use exemplos genéricos e explique comandos, pré-requisitos, efeito local e limitações. Não apresente resultados de benchmark ou compatibilidade de plataforma sem evidência reproduzível. Separe o comportamento validado das possibilidades ainda não verificadas.
