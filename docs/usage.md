# Uso

## 1. Configurar o ambiente

Instale Python 3.12. Clone o repositório e entre na pasta do projeto:

```powershell
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
Set-Location secon-dbrain-mcp
```

Na raiz do projeto:

```powershell
python Sistema/setup_environment.py
```

Para indicar o caminho de uma instalação específica:

```powershell
python Sistema/setup_environment.py --python 'C:\caminho\para\python.exe'
```

Isso cria `.venv` no projeto e instala as dependências isoladamente. Prepare o modelo fixado de embeddings uma vez, com conexão à rede:

```powershell
.\dbrain.ps1 setup-model
```

O modelo fica em `.dbrain/`. Depois de baixado, a consulta e a indexação não precisam de acesso de rede. O modo lexical não usa modelo, mas é uma escolha explícita ao criar uma coleção lexical.

No Windows, use o wrapper `dbrain.ps1`. Em Linux/macOS, use `.venv/bin/python Sistema/dbrain.py`. Nestes exemplos Unix, substitua o prefixo Windows por esse executável e passe os mesmos subcomandos.

Para operar sobre outra raiz sem mudar o diretório atual, passe `--root` antes do subcomando:

```powershell
.\.venv\Scripts\python.exe Sistema/dbrain.py --root 'D:\MinhaColecao' update
```

Use sempre o Python de `.venv` para a CLI nesse caso. A raiz externa precisa ter `Sistema/config.json`, `Sistema/schema.json`, `90-Templates/` e as pastas de origem configuradas; uma pasta contendo somente PDFs não basta.

## 2. Adicionar fontes e indexar

Coloque PDFs em `Documentos/` e notas em Markdown em `Notas/`. Para adicionar sua própria fonte, por exemplo:

```powershell
Copy-Item 'C:\meus-arquivos\manual.pdf' '.\Documentos\manual.pdf'
Set-Content '.\Notas\meu-resumo.md' "# Meu resumo`n`nAnotações próprias sobre o tema."
```

Atualize o índice completo ou indique somente a fonte/pasta que mudou:

```powershell
.\dbrain.ps1 update
.\dbrain.ps1 update --path '.\Documentos\manual.pdf'
.\dbrain.ps1 update --path '.\Notas'
```

Para PDFs com páginas digitalizadas, OCR por Tesseract é opcional e seletivo. Configure apenas as páginas necessárias em `Sistema/config.json` e instale Tesseract conforme as instruções do projeto. A extração OCR fica em `.dbrain/`, nunca substitui o PDF original. Confira o resultado visualmente, especialmente tabelas, código e colunas.

O modo lexical é uma alternativa para uma nova coleção ou ambiente sem modelo:

```powershell
.\dbrain.ps1 update --lexical
```

Ele constrói um índice sem embeddings. Não converta uma coleção híbrida existente para lexical com esse comando; a mudança de modalidade requer reconstrução deliberada e reindexação.

## 3. Buscar e conferir trechos

```powershell
.\dbrain.ps1 search 'pergunta sobre o conteúdo'
.\dbrain.ps1 search 'termos exatos' --limit 5
.\dbrain.ps1 read 'source-id' --page 12
.\dbrain.ps1 status
```

Use o identificador e localizador retornados pela busca para abrir a evidência correspondente. Resultados em PDF informam página física; Markdown informa seção/linha. A leitura é limitada às fontes cadastradas no índice, não a caminhos arbitrários.

## 4. Conectar via MCP (opcional)

Gere a configuração MCP para um cliente compatível:

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target generic
```

O instalador mostra a configuração JSON gerada. Para aplicar diretamente a uma integração específica, escolha `codex` ou `claude` e inclua `--apply`:

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target codex --apply
.venv\Scripts\python.exe Sistema/install_agents.py --target claude --apply
```

Use `--root PATH` para apontar a outra cópia da coleção e `--python PATH` para definir o interpretador usado na configuração. Sem `--apply`, a instalação é apenas simulada/relatada. Reabra ou atualize a sessão do cliente após aplicar a configuração.

O servidor MCP disponibiliza `search_knowledge`, `read_knowledge` e `knowledge_status`. As ferramentas são somente de leitura. `knowledge_status` pode detectar mudanças em arquivos já conhecidos, mas não adiciona arquivos nem inicia indexação.

## 5. Criar notas com templates (opcional)

Os oito arquivos de `90-Templates/` são modelos Markdown genéricos. Copie ou insira o template adequado no seu editor e escreva sua nota em `Notas/`. Para criar uma nota pela CLI, por exemplo:

```powershell
.\dbrain.ps1 new --type concept --title 'Minha ideia' --areas geral --by human
```

O esquema geral usa `areas: [geral]`. Para uma coleção de segurança, há um perfil opcional em `Sistema/profiles/security/schema.json`; ative-o definindo `schema_file` para esse caminho em `Sistema/config.json`. Mantenha metadados legíveis e registre fontes e localização para permitir conferência. Obsidian pode facilitar a navegação e a inserção de modelos, mas não é necessário para indexar Markdown.

A skill genérica é um arquivo opcional, independente do MCP. O instalador das integrações Codex e Claude instala a skill automaticamente; não há um comando genérico de instalação manual documentado.

## Como interpretar respostas

RAG recupera contexto durante a pergunta; não significa que o modelo aprendeu ou foi treinado com a coleção. A busca combina correspondência lexical e semelhança vetorial no modo padrão. O modelo de linguagem que responde pode receber os trechos encontrados, conforme a integração e o provedor escolhidos. Nunca indexe segredos; também não indexe dados que não devem ser enviados ao serviço da conversa.

Trechos e pontuações não demonstram que uma afirmação está correta ou atual. Confirme passagens importantes na fonte e na versão aplicável. PDFs podem ter texto ausente ou extração imperfeita; OCR é incerto e exige revisão. A ferramenta aceita PDF e Markdown como fontes, não EPUB, DOCX, HTML ou páginas obtidas por scraping. Não disponibiliza uma API HTTP.
