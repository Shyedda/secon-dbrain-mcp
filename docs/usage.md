# Uso

Este guia conduz da cópia do projeto até uma busca local e, se você quiser, à conexão com um cliente de IA. O SecOn Dbrain funciona sem Obsidian e sem MCP; use qualquer editor de texto para criar arquivos Markdown.

## O que a ferramenta faz

O trabalho tem duas fases. **Na indexação**, a ferramenta extrai PDF e Markdown, registra metadados e localizadores, divide o texto em trechos de até 400 tokens com sobreposição de até 40 tokens e calcula embeddings com `intfloat/multilingual-e5-small` em CPU via ONNX. Esses vetores multilíngues têm 384 dimensões e são normalizados.

**Na consulta**, SQLite FTS5 faz a busca lexical BM25, NumPy compara vetores por similaridade de cosseno e a fusão RRF combina as listas de candidatos. A resposta inclui localizadores como página física de PDF ou seção/linhas de Markdown. RAG significa que um cliente de IA pode consultar esses trechos durante a conversa e usá-los como contexto; isso não faz fine-tuning nem treina o modelo com sua coleção. O MCP só lê o índice.

## 1. Clonar e preparar o ambiente

Python 3.12 é necessário. O instalador cria `.venv` dentro da cópia do projeto e instala as dependências sem usar os pacotes Python do sistema.

### Windows

Instale Git e Python 3.12. Abra PowerShell, confirme a versão e clone o projeto:

```powershell
python --version
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
Set-Location secon-dbrain-mcp
python Sistema/setup_environment.py
```

Se `python` apontar para outra versão, ajuste o PATH para Python 3.12 ou informe o executável explicitamente:

```powershell
python Sistema/setup_environment.py --python 'C:\caminho\para\python.exe'
```

Use o Python do ambiente do projeto para os comandos seguintes. O wrapper PowerShell `dbrain.ps1` é opcional e não é necessário habilitar a execução de scripts:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py status
```

### Ubuntu 24.04 x86_64

Instale Git, Python 3.12 e o pacote de ambientes virtuais, clone e prepare o ambiente:

```bash
sudo apt update
sudo apt install git python3.12 python3.12-venv
python3.12 --version
git clone https://github.com/Shyedda/secon-dbrain-mcp.git
cd secon-dbrain-mcp
python3.12 Sistema/setup_environment.py
.venv/bin/python Sistema/dbrain.py status
```

Este guia cobre Windows e Ubuntu 24.04 x86_64.

## 2. Baixar o modelo local

Na primeira configuração do índice híbrido, baixe explicitamente o modelo fixado pelo projeto. Este passo precisa de rede:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py setup-model
```

No Ubuntu:

```bash
.venv/bin/python Sistema/dbrain.py setup-model
```

O modelo fica nos dados locais em `.dbrain/`. Depois do download, indexação e busca podem ser feitas localmente, sem conexão à rede. O modo lexical dispensa embeddings e modelo, mas é uma modalidade alternativa explícita para uma coleção nova; não o use para substituir o índice híbrido já criado.

## 3. Entender as pastas

Na primeira execução, use as pastas abaixo para separar fontes originais, conhecimento próprio e arquivos de suporte. Coloque conteúdo pessoal somente na sua cópia local. O Git ignora o conteúdo do usuário; a distribuição mantém os READMEs de orientação e os oito templates opcionais.

| Pasta | O que guardar | Entra na busca? |
|---|---|---|
| `00-Inicio/` | Orientações e mapas próprios em Markdown | Sim |
| `10-Fontes/` | Fichas bibliográficas e estudos de caso em Markdown; fichas de livros ficam em `10-Fontes/Livros/` | Sim |
| `20-Notas/` | Conceitos e anotações próprias em Markdown | Sim |
| `30-Procedimentos/` | Procedimentos, checklists e ferramentas em Markdown | Sim |
| `40-Experimentos/` | Experimentos e writeups em Markdown | Sim |
| `Livros/` | Livros em PDF | Sim |
| `Documentos/` | Manuais, documentações e relatórios em PDF | Sim |
| `Markdown/` | Documentação de referência original em `.md` | Sim |
| `Anexos/` | Imagens e evidências | Não |
| `90-Templates/` | Oito modelos Markdown opcionais para criar notas | Não |
| `Sistema/` | Código e configuração | Não |

Cada pasta tem um README próprio para explicar seu uso. Esses arquivos de orientação são excluídos da indexação por `rag_exclude: true`. Não coloque PDFs dentro das pastas de notas: use `Livros/` ou `Documentos/`. O Obsidian é opcional e pode ajudar a navegar, mas não é necessário para ler ou indexar Markdown.

### Personalizar a coleção (opcional)

Você pode usar a coleção sem editar a configuração. Se quiser mudar a organização, ajuste `Sistema/config.json`:

| Propriedade | Para que serve |
|---|---|
| `include` | Pastas que entram na indexação |
| `pdf_roots` | Pastas onde PDFs são tratados como fontes PDF |
| `note_dirs` | Pasta associada a cada tipo de nota criado pela CLI |
| `schema_file` | Caminho do vocabulário de áreas, tipos e metadados |

O esquema geral vem com a área `geral`; use-a ao criar notas próprias. Um perfil opcional de segurança está em `Sistema/profiles/security/schema.json`; para usá-lo, ajuste `schema_file` no arquivo de configuração. Consulte também os demais campos de `Sistema/config.json` antes de personalizar. Na distribuição básica, a configuração já aponta para as pastas apresentadas acima.

## 4. Adicionar arquivos PDF e Markdown

No Windows, crie um arquivo de nota e copie um PDF de exemplo:

```powershell
New-Item -ItemType Directory -Force 'Documentos' | Out-Null
Copy-Item 'C:\meus-arquivos\manual.pdf' '.\Documentos\manual.pdf'
Set-Content '.\20-Notas\meu-resumo.md' "# Meu resumo`n`nAnotações próprias sobre o tema."
```

No Ubuntu:

```bash
mkdir -p Documentos
cp "$HOME/arquivos/manual.pdf" Documentos/manual.pdf
cat > 20-Notas/meu-resumo.md <<'EOF'
# Meu resumo

Anotações próprias sobre o tema.
EOF
```

Você também pode criar e editar os arquivos no seu editor habitual. Markdown sem frontmatter YAML é aceito. Um frontmatter ajuda a organizar notas, mas não é obrigatório para uma busca básica. Os modelos em `90-Templates/` são opcionais.

Para criar uma nota com a CLI, por exemplo:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py new --type concept --title 'Minha ideia' --areas geral --by human
```

No Ubuntu, use `.venv/bin/python` no início do comando. Estes são os tipos e suas pastas padrão:

| Tipo | Pasta |
|---|---|
| `source`, `case-study` | `10-Fontes/` |
| `concept` | `20-Notas/` |
| `procedure`, `checklist`, `tool` | `30-Procedimentos/` |
| `experiment`, `writeup` | `40-Experimentos/` |

Os oito templates em `90-Templates/` são opcionais e podem ser usados no editor que preferir; `new` usa o template correspondente ao tipo. A skill `secon-dbrain` também é opcional: ela ensina um agente compatível a consultar e citar a biblioteca. MCP e skill são independentes.

Atualize o índice depois de adicionar ou mudar arquivos:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py update
```

No Ubuntu:

```bash
.venv/bin/python Sistema/dbrain.py update
```

Para uma mudança pequena, atualize somente o arquivo ou pasta afetada:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py update --path 'Documentos/manual.pdf'
.venv\Scripts\python.exe Sistema/dbrain.py update --path '20-Notas/meu-resumo.md'
```

O PDF original permanece no lugar. A indexação gera dados locais em `.dbrain/`; não copie nem versione essa pasta como se fosse conteúdo de origem.

## 5. Conferir e buscar

Confira estado e consistência e faça uma consulta pela CLI:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py status
.venv\Scripts\python.exe Sistema/dbrain.py check
.venv\Scripts\python.exe Sistema/dbrain.py search 'o que a fonte diz sobre o tema'
```

No Ubuntu, use `.venv/bin/python` no início de cada comando. A busca mostra IDs de fonte e localizadores. Leia uma fonte pelo `source_id` apresentado:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py read 'source-id' --page 1
```

Substitua `1` por uma página física que exista no PDF. Para Markdown, use somente o ID da fonte, sem `--page`; o resultado de leitura identifica a seção e as linhas. Resultados são sugestões de trechos relevantes, não prova de que uma afirmação esteja correta ou atual. Compare os trechos com a fonte completa e sua versão. PDFs digitalizados ou com tabelas, colunas e imagens podem exigir conferência visual.

### OCR opcional para PDFs digitalizados

OCR com Tesseract é opcional. Use-o de forma seletiva: instale Tesseract no sistema, configure em `Sistema/config.json` as páginas físicas do PDF que precisam de OCR e solicite a reextração somente desse arquivo. Por exemplo, para as páginas físicas 3 e 4 de um arquivo chamado `manual-digitalizado.pdf`, a configuração inclui:

```json
{
  "ocr": {
    "language": "eng+por",
    "pages": {
      "manual-digitalizado.pdf": [3, 4]
    }
  }
}
```

Preserve as demais propriedades do arquivo de configuração ao editar esse trecho:

```powershell
.venv\Scripts\python.exe Sistema/dbrain.py update --path 'Documentos/manual-digitalizado.pdf' --reextract
```

No Ubuntu, o mesmo comando usa `.venv/bin/python`. As páginas são contadas como páginas físicas do PDF. O OCR pode errar; confira o texto extraído e as citações na imagem da página. Não configure páginas sem necessidade e não presuma que OCR recuperará todo o conteúdo visual.

## 6. Conectar um cliente de IA pelo MCP (opcional)

O servidor MCP roda localmente como processo STDIO, sem servidor HTTP. Ele expõe três ferramentas somente de leitura:

- `search_knowledge`: busca trechos e retorna fonte e localizador.
- `read_knowledge`: lê o trecho de uma fonte indexada.
- `knowledge_status`: informa o estado do índice, sem indexar arquivos novos.

Gere a configuração genérica:

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target generic
```

No Ubuntu:

```bash
.venv/bin/python Sistema/install_agents.py --target generic
```

O instalador genérico apenas imprime uma configuração; não altera o cliente. Use um cliente que ofereça suporte a MCP via STDIO e permita que o modelo chame ferramentas. Se o cliente aceitar a estrutura `mcpServers`, copie o JSON gerado. Caso use outro formato, cadastre os mesmos valores de `command`, `args` e `env` nos campos equivalentes do cliente. O JSON aponta para caminhos absolutos desta cópia do projeto; mantenha-a no local e não cole caminhos de outra máquina.

Após salvar a configuração, reinicie a sessão do cliente para carregar o servidor. Peça ao modelo para pesquisar a coleção, ler os trechos que sustentam a resposta e citar o título da fonte com a página física do PDF ou a seção/linhas do Markdown. Se não houver evidência suficiente na coleção, peça que diga isso. MCP e cliente são componentes separados; instalar ou configurar um não faz todos os modelos ou serviços passarem a consultá-lo automaticamente.

Codex e Claude podem usar o instalador para cadastrar a integração e instalar as instruções e a skill opcional:

```powershell
.venv\Scripts\python.exe Sistema/install_agents.py --target codex --apply
.venv\Scripts\python.exe Sistema/install_agents.py --target claude --apply
```

Esse passo altera a configuração do cliente selecionado. Sem `--apply`, integrações específicas só são simuladas e relatadas. A configuração genérica não se aplica automaticamente a todos os clientes. `--root` no instalador vem depois do script, por exemplo `Sistema/install_agents.py --target generic --root 'D:\MinhaColecao'`. Para a CLI, `--root` vem antes do subcomando: `Sistema/dbrain.py --root 'D:\MinhaColecao' status`.

## 7. Privacidade e limites

Extração, embeddings, índice e consulta pela CLI são locais. Quando o MCP fornece trechos a um cliente, esses trechos podem ser enviados ao provedor de IA usado naquela conversa; o tratamento depende do cliente e do serviço escolhido. Não indexe credenciais, segredos ou documentos que você não pode compartilhar com esse provedor. Resultados podem estar incompletos, desatualizados ou fora de contexto e não oferecem garantia factual.

A ferramenta trabalha com PDF e Markdown; não é um leitor geral de EPUB, DOCX, HTML ou páginas web. Ela não faz scraping, fine-tuning nem disponibiliza uma API HTTP.

## Compatibilidade com coleções existentes

Este trecho é para quem já tinha uma coleção antes da estrutura atual. A configuração continua indexando PDFs antigos em `Documentos/`. Uma pasta `Notas/` de uma coleção antiga também pode continuar no escopo de indexação para compatibilidade; novas notas devem ir para `20-Notas/`. Em um clone novo, `Notas/` não é uma pasta de conteúdo distribuída. Preserve arquivos existentes e confira os escopos em `Sistema/config.json` antes de reorganizar uma coleção.

Para outra configuração de coleção, passe `--root` à CLI antes do subcomando. A raiz precisa conter a configuração e os esquemas esperados pelo projeto, além das pastas correspondentes. Uma pasta que contém apenas PDFs não é uma coleção completa.

Volte ao [README](../README.md) do projeto para a visão geral.
