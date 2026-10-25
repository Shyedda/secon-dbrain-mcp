# Uso

Este guia mostra como preparar uma coleção local de fontes PDF e Markdown, pesquisar as evidências e, opcionalmente, conectar um cliente de IA ou criar resumos derivados. Obsidian e MCP são opcionais; qualquer editor de texto serve para os arquivos Markdown.

## Pastas e camadas

A distribuição usa esta estrutura:

| Caminho | Papel | Entra na busca? |
|---|---|---|
| `PDFs/` | Fontes originais PDF (Bronze) | Sim |
| `Markdown/` | Fontes originais Markdown (Bronze) | Sim |
| `Conhecimento/00-Inicio/` | Orientações e mapas da biblioteca | Sim |
| `Conhecimento/10-Fontes/` | Fichas bibliográficas e estudos de caso | Sim |
| `Conhecimento/20-Notas/` | Resumos e conceitos derivados | Sim |
| `Conhecimento/30-Procedimentos/` | Procedimentos e checklists derivados por curadoria | Sim |
| `Conhecimento/40-Experimentos/` | Sínteses de experimentos documentados nas fontes | Sim |
| `Conhecimento/90-Templates/` | Templates opcionais | Não |
| `.dbrain/` | Índice, cache e derivados técnicos regeneráveis (Silver) | Não é fonte |

Na distribuição genérica, as entradas padrão são `PDFs/` e `Markdown/`. A configuração `input_dirs` define as pastas de fontes de cada biblioteca; em uma cópia privada preexistente, caminhos como `Livros/` podem continuar configurados para PDF. Preserve bytes, nomes e localização dos originais, sem movê-los para corresponder ao exemplo público. Derivados ficam em `knowledge_dir` (padrão `Conhecimento/`). Os guias README têm `rag_exclude: true`; templates nunca entram na busca. As cópias pública e privada usam a mesma implementação, mas podem manter configurações, esquemas, templates, skills personalizadas e acervos diferentes. O repositório privado pode continuar versionando suas notas e resumos. O pacote público exportado não inclui originais, notas nem resumos da coleção privada.

A camada **Silver** contém texto extraído, trechos, embeddings, FTS5, índice vetorial, fusão RRF e mapas heurísticos locais baseados em termos, sem afirmar relações semânticas verificadas. São derivados para recuperação e não provam que toda a fonte foi entendida. A camada **Gold** é formada por resumos opcionais e progressivos gerados pelo assistente em tarefas delimitadas, com citações para unidades retornadas. Resumos são Markdown derivado em `Conhecimento/`, com `status: needs-review` até revisão. Não trate nenhum índice ou resumo como garantia de conhecimento completo ou acurácia.

## 1. Instalar (Windows e Ubuntu 24.04)

É necessário Python 3.12 e Git. A instalação cria `.venv` dentro da cópia do projeto.

Windows, no PowerShell:

```powershell
python --version
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
Set-Location secon-dbrain-mcp
python Sistema/setup_environment.py
.venv\Scripts\python.exe Sistema/dbrain.py setup-model
```

Ubuntu 24.04 x86_64:

```bash
sudo apt update
sudo apt install git python3.12 python3.12-venv
python3.12 --version
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
cd secon-dbrain-mcp
python3.12 Sistema/setup_environment.py
.venv/bin/python Sistema/dbrain.py setup-model
```

`setup-model` baixa o modelo fixado pelo projeto e precisa de rede. Depois disso, a preparação híbrida e a busca podem rodar localmente em CPU. O modo `--lexical` não exige embeddings. Use o mesmo modo de índice já escolhido ao preparar atualizações.

## 2. Adicionar fontes e conhecimento próprio

Coloque os originais nas pastas que aparecem em `Sistema/config.json` em `input_dirs`. No perfil público padrão, use `PDFs/` e `Markdown/`; uma biblioteca já configurada pode continuar usando, por exemplo, `Livros/` para PDF. Não mova originais para encaixá-los no guia. Anotações e derivados pertencem às subpastas de `knowledge_dir` (padrão `Conhecimento/`).

Exemplo para o perfil público padrão (ajuste o destino para sua configuração local):

PowerShell:

```powershell
Copy-Item 'C:\meus-arquivos\manual.pdf' '.\PDFs\manual.pdf'
Set-Content '.\Conhecimento\20-Notas\minha-nota.md' "# Minha nota`n`nSíntese própria com as fontes consultadas."
```

Ubuntu:

```bash
cp "$HOME/arquivos/manual.pdf" PDFs/manual.pdf
cat > Conhecimento/20-Notas/minha-nota.md <<'EOF'
# Minha nota

Síntese própria com as fontes consultadas.
EOF
```

Arquivos em `Conhecimento/90-Templates/` servem para iniciar novas notas, mas não são indexados. Não preencha ou salve conhecimento nessa pasta. A pasta `.dbrain/` guarda dados locais do índice e cache e não deve ser tratada como conteúdo de origem.

## 3. Preparar e atualizar a busca

Use `prepare` para sincronizar alterações nas fontes, atualizar os mapas heurísticos e indexar os derivados elegíveis em `Conhecimento/`. A preparação completa inicial pode demorar; execute em terminal próprio para que o processo possa terminar. A operação incremental de arquivos existentes deve ser preferida em alterações comuns. Os mapas gerados atuais são `Conhecimento/00-Inicio/Mapa geral do acervo.md` e `Mapa de temas.md`. IDs de notas permanecem estáveis; o histórico dos mapas gerados fica local em `.dbrain/knowledge/history/maps/`. Os mapas são auxiliares heurísticos, sem promessa de cobertura integral.

Windows:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py prepare --wait 900
.venv\Scripts\python.exe Sistema/dbrain.py prepare --path 'PDFs/manual.pdf' --wait 900
```

Ubuntu:

```bash
.venv/bin/python Sistema/dbrain.py prepare --wait 900
.venv/bin/python Sistema/dbrain.py prepare --path 'Markdown/referencia.md' --wait 900
```

Opções previstas para `prepare`:

- `--path`: limita a operação a caminho(s) alterados, quando suportado pela CLI.
- `--lexical`: usa a modalidade lexical sem embeddings. Mantenha a modalidade consistente com o índice existente.
- `--wait 900`: aguarda até 900 segundos pela trava do escritor; se continuar ocupada, aguarde e tente depois. Nunca apague `writer.lock`.
- `--by agent`: registra a proveniência operacional do agente que produziu uma escrita. Não representa autoria no Git.

A CLI também expõe `status`, `check`, `search` e `read` para consultar o estado e conferir evidências. Use a ajuda do comando para os parâmetros específicos. O wrapper PowerShell `dbrain.ps1` pode ser usado no Windows no lugar de `Sistema/dbrain.py`.

## 4. Pesquisar e conferir evidências

Pesquise um tema e leia os trechos retornados antes de responder. Cite o título/origem e a localização fornecida: página física do PDF ou seção/linhas do Markdown. As páginas e localizadores podem se referir à extração; confira afirmações importantes na fonte original, especialmente em PDFs digitalizados, tabelas, colunas, código ou diagramas.

A busca híbrida combina recuperação lexical FTS5, similaridade vetorial e fusão RRF. Mapas heuristicamente gerados ajudam a navegar, mas podem deixar de fora ou classificar conteúdo incorretamente. Os resultados são candidatos de recuperação; não constituem prova de exaustividade, correção ou atualidade.

O OCR com Tesseract pode ser habilitado seletivamente nas páginas necessárias, se disponível na instalação. Confira visualmente o resultado OCR e sua citação. Não presuma que OCR recupera todo conteúdo visual.

## 5. Conectar um cliente por MCP

O servidor local usa transporte STDIO. As ferramentas MCP de leitura são `search_knowledge`, `read_knowledge`, `knowledge_status`, `knowledge_overview` e `read_enrichment_task`. A busca e a leitura retornam trechos e localizadores que o agente deve citar.

Gere a configuração genérica do cliente (Windows):

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target generic
```

Para imprimir uma configuração que habilite os escritores, acrescente `--allow-writes`. O instalador não altera o cliente genérico; copie a saída para ele. As integrações específicas também aceitam essa opção quando forem aplicadas.

No Ubuntu, use `.venv/bin/python Sistema/install_agents.py --target generic` (ou acrescente `--allow-writes` para incluir os escritores MCP). Cadastre os valores exibidos nos campos MCP equivalentes do cliente e reinicie a sessão. O formato `mcpServers` é aceito por alguns clientes; outros usam sua própria estrutura de configuração.

A preparação inicial completa pode levar tempo e é melhor executada pela CLI em terminal próprio. `prepare_knowledge(paths?)` é opcional para atualizações menores e só aparece com `--allow-writes`. O instalador genérico aceita `--allow-writes` e imprime a configuração correspondente; sem essa opção, o MCP fica em leitura.

Quando conectado, `read_enrichment_task` é sempre disponível para leitura. `plan_enrichment` e `submit_enrichment` só são registrados com `--allow-writes`, pois criam registros e resumos. Leia a skill `dbrain-enrichment` antes de solicitar essa tarefa. O conteúdo lido pode ser enviado ao provedor de IA escolhido para a conversa.

### Checklist rápido e prompts

1. **Prepare o índice pela CLI** depois de adicionar fontes ou na primeira configuração. No Windows, use `.venv\Scripts\python.exe Sistema/dbrain.py prepare --wait 900`; no Ubuntu, `.venv/bin/python Sistema/dbrain.py prepare --wait 900`. Para uma alteração pequena, acrescente `--path '<caminho relativo>'` ao comando da sua plataforma.
2. **Gere a configuração MCP** a partir da pasta do projeto: `.venv\Scripts\python.exe Sistema/install_agents.py --target generic` (Windows) ou `.venv/bin/python Sistema/install_agents.py --target generic` (Ubuntu). O comando imprime a configuração STDIO; ele não instala nem altera o cliente.
3. **Copie/adapte a configuração exibida** para o arquivo ou campo MCP do seu cliente. O instalador fornece o comando Python, o caminho do servidor e a raiz desta cópia; clientes podem usar formatos diferentes do exemplo `mcpServers`.
4. **Recarregue o cliente ou inicie uma nova sessão** para ele abrir o servidor local.
5. Peça ao cliente para chamar `knowledge_status`. A resposta deve mostrar o estado/cobertura do índice, incluindo fontes conhecidas e possíveis diferenças em relação aos arquivos. Essa ferramenta só consulta o estado: não descobre arquivos novos nem os indexa. Se a fonte esperada não estiver indexada, prepare-a pela CLI e consulte o status novamente.

Depois da conexão, você conversa normalmente com o assistente. Copie um dos prompts abaixo e substitua os campos entre `<...>`:

#### Confirmar a conexão

```text
Verifique se o MCP SecOn Dbrain está conectado e se minha biblioteca está indexada. Informe se há algum problema ou material desatualizado.
```

#### Pesquisar um assunto

```text
Pesquise na biblioteca como <assunto> funciona. Use search_knowledge com limit=5; leia com read_knowledge os 1 ou 2 trechos mais relevantes, usando source_id e locator retornados. Responda apenas o que as evidências sustentam e cite título, fonte e página física do PDF ou seção/linhas do Markdown. Aponte lacunas.
```

#### Comparar materiais

```text
Compare o que <documento A ou assunto A> e <documento B ou assunto B> dizem sobre <assunto>. Busque evidências para cada um com até 5 resultados por busca, leia 1 ou 2 trechos de cada documento e cite separadamente fonte e página física/seção. Diferencie concordâncias, diferenças e pontos que os trechos não permitem concluir.
```

#### Conferir uma evidência

```text
Leia a evidência identificada por source_id=<source_id> e locator=<locator retornado pela busca> usando read_knowledge. Explique o que este trecho afirma e o que ele não demonstra. Cite a origem e a página física/seção retornada.
```

#### Investigar uma busca sem resultados

```text
Não encontrei resultados para <assunto>. Consulte knowledge_status e tente uma busca mais específica e outra com sinônimos ou termos em inglês, com limit=5 em cada uma. Se continuar sem resultado, diga isso claramente e indique se a fonte parece ausente ou ainda não preparada; não invente conteúdo.
```

#### Limitar o contexto e os tokens

```text
Responda à pergunta <pergunta> economizando contexto: use search_knowledge com limit=3 (no máximo 5) e leia somente 1 ou 2 trechos com read_knowledge. Cite fonte e página física/seção; informe quando a evidência disponível for insuficiente.
```

#### Preparar um resumo pequeno (opcional)

```text
Opcional, apenas se este MCP foi iniciado com --allow-writes: chame plan_enrichment(query="<assunto>", source_ids=["<source_id>"], max_tasks=2, max_input_tokens=4000). Leia cada tarefa com read_enrichment_task(task_id) e sintetize somente o trecho e a referência recebidos, usando [0] nas afirmações sustentadas. Não invente fatos, páginas ou resultados. Só se eu pedir para gravar, use submit_enrichment(task_id, title, summary, citations=[0], by="agent") com [0] literal no resumo.
```

`search_knowledge` retorna candidatos, trechos e localizadores; `read_knowledge` lê o trecho/página/seção da fonte selecionada, não o livro inteiro. Use o localizador devolvido pela busca para ligar a leitura à evidência encontrada. O MCP disponibiliza contexto ao modelo durante a conversa; não treina o modelo. O grafo do Obsidian é uma visualização opcional de links entre notas: não é o índice vetorial nem prova de que uma resposta está correta.

## 6. Enriquecer por lotes (opcional)

Enriquecimento cria resumos derivados com evidências citadas. Planeje apenas o tema ou as fontes que respondem à necessidade atual; não tente processar a coleção inteira por padrão. Limite o número de tarefas e o orçamento de tokens, leia cada tarefa antes de produzir o resumo e use somente os IDs de citação/unidades retornados naquela tarefa.

CLI:

```text
dbrain.py enrichment-plan [--query TEMA] [--source-id ID] [--max-tasks 3] [--max-input-tokens 4000]
dbrain.py enrichment-read TASK_ID
dbrain.py enrichment-submit TASK_ID --file resumo.json --by agent
```

`max_tasks` aceita de 1 a 10 tarefas. `max_input_tokens` aceita de 1000 a 12000 e estima o orçamento de entrada por tarefa; não é garantia de tokens cobrados pelo provedor. Cada tarefa contém apenas um segmento parcial de uma unidade de uma fonte, não um capítulo completo nem prova de cobertura. Planeje apenas o lote necessário; não processe a biblioteca inteira por padrão.

MCP equivalente, disponível somente com `--allow-writes` para planejamento e envio:

```text
plan_enrichment(query?, source_ids?, max_tasks=3, max_input_tokens=4000)
read_enrichment_task(task_id)  # leitura disponível mesmo sem --allow-writes
submit_enrichment(task_id, title, summary, citations: list[int], by='agent')
```

`read_enrichment_task` retorna uma lista `references` com uma única referência identificada como citação `0`. Use essa referência para citar as afirmações sustentadas pelo trecho: o corpo de `summary` deve conter literalmente `[0]` e `citations` precisa ser exatamente `[0]`. O arquivo passado em `--file` é JSON, por exemplo `{"title":"Síntese parcial","summary":"Afirmação limitada ao trecho da fonte [0].","citations":[0]}`. O título deve ter até 200 caracteres em uma linha; o resumo deve ter de 20 a 16000 caracteres.

O envio cria um Markdown derivado em `Conhecimento/20-Notas/`, indexa-o e registra `source_refs` com o hash e os localizadores da fonte. A nota nasce em `needs-review`. A validação verifica a estrutura da citação e a versão da fonte, mas não a fidelidade semântica do resumo. A busca exclui derivados quando detecta mudanças pela versão indexada ou pelo tamanho/data dos arquivos. A leitura de Gold também verifica o hash real da fonte e recusa a síntese se os bytes divergirem. Sempre leia o resultado antes de fundamentar a resposta. Execute `prepare` e planeje uma tarefa nova para fontes alteradas. Não invente fatos, páginas, resultados ou experimentos executados. O fluxo usa trechos no contexto do assistente, não treina o modelo e não faz chamadas a uma API de geração do projeto.
## 7. Privacidade e limites

### Comparar a implementação entre repositórios

As configurações e o conteúdo da coleção podem diferir entre cópias que usam o mesmo código. Para conferir se a implementação está alinhada, execute a partir da cópia de referência:

```powershell
.venv\Scripts\python.exe Sistema/runtime_manifest.py --check
.venv\Scripts\python.exe Sistema/runtime_manifest.py --compare 'C:\caminho\para\outra-copia'
```

No Ubuntu, use `.venv/bin/python` no lugar do executável Windows. O manifesto compara fingerprints de código, testes, skills genéricas e guia de uso. Ele exclui config/schema da coleção, corpus, templates, skill personalizada e README do acervo, pois esses arquivos podem ser específicos de cada biblioteca. Ao publicar mudanças na implementação, exporte o pacote público a partir do mesmo código e valide os fingerprints; isso é uma etapa manual, não uma sincronização automática.

### Personalizar o contexto da coleção

O esquema inicial em `Sistema/schema.json` contém somente a área `geral`, sem um perfil profissional predefinido. Acrescente suas próprias áreas nesse arquivo e use seus identificadores nos metadados das notas. `list_fields`, `patterns` e `filters` permitem definir campos de classificação adequados à sua coleção; campos listados em `list_fields` devem conter listas no YAML. O parâmetro `schema_file` em `Sistema/config.json` também permite apontar para outro esquema local.

Sinônimos opcionais de busca ficam em `lexical_expansions`, no formato `{"termo": "termo equivalente"}`, em `Sistema/config.json`; o padrão é vazio. Essas configurações são escolhas da sua instalação. Não inclua preferências, caminhos, instruções ou conteúdo pessoal em contribuições públicas. Confira o diff dos arquivos de configuração antes de publicar.

Arquivos originais permanecem sob controle da coleção e devem ser preservados. O repositório privado pode versionar notas e resumos para manter seu histórico; o pacote público exportado fica sem esses conteúdos e sem os originais. Índices, embeddings, extrações, cache e outros derivados técnicos ficam em `.dbrain/` e são dados locais regeneráveis. Confira `git status` e o conteúdo exportado antes de compartilhar uma alteração.

Trechos retornados pelo MCP podem ser enviados ao provedor de IA usado na conversa. Não indexe credenciais, segredos ou conteúdo que não possa ser compartilhado com esse serviço. Extração e recuperação têm limites, mapas heurísticos podem errar e resumos opcionais podem omitir contexto. Valide na fonte antes de usar uma afirmação como fato. Nunca registre um experimento como executado sem evidência de que foi realizado.

Consulte também o [README](../README.md) e os guias em `Conhecimento/`.
