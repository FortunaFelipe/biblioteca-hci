# Instruções para agentes

Este projeto é um sistema local de controle de biblioteca corporativa para os livros de endomarketing da HCI.

## Objetivo do sistema

Manter um controle simples de:

- livros cadastrados;
- empréstimos em aberto;
- devoluções;
- dias em que cada livro está com um colaborador;
- histórico exportável em CSV.

O foco é operação interna, clareza e baixo atrito para quem vai registrar empréstimos e devoluções.

## Stack atual

- Python
- Streamlit
- SQLite

Arquivos principais:

- `app.py`: aplicação Streamlit e regras de negócio.
- `requirements.txt`: dependências Python.
- `README.md`: instruções para pessoas usuárias.
- `data/biblioteca.db`: banco SQLite criado automaticamente em runtime. Não versionar.
- `Brandbook HCI Advisors v2.pdf`: referência de marca, cores, tipografia e elementos gráficos.

## Como executar

No ambiente atual, o Python conhecido é:

```powershell
& 'C:\Users\felip\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m streamlit run app.py
```

Quando `python` estiver disponível no PATH, também pode funcionar:

```powershell
python -m streamlit run app.py
```

## Como validar mudanças

Sempre que alterar Python, rode pelo menos:

```powershell
& 'C:\Users\felip\AppData\Local\Python\pythoncore-3.14-64\python.exe' -m py_compile app.py
```

Se o app estiver rodando, confira a tela principal em:

```text
http://127.0.0.1:8501
```

## Regras de desenvolvimento

- Preserve a simplicidade: este é um app operacional interno, não uma plataforma complexa.
- Evite dependências novas sem necessidade clara.
- Mantenha o banco SQLite compatível com dados já existentes.
- Não apague nem recrie `data/biblioteca.db` sem pedido explícito do usuário.
- Não versionar banco, caches ou artefatos locais.
- Ao mudar schema, prefira migrações compatíveis com bancos já criados.
- Mantenha labels e textos da interface em português do Brasil.
- Priorize fluxos completos: cadastrar livro, cadastrar colaborador, emprestar, devolver e consultar histórico.
- Use componentes nativos do Streamlit quando forem suficientes.
- Antes de refatorar visual ou estrutura, preserve o comportamento já existente.

## Modelo de dados atual

Tabelas:

- `books`: cadastro de livros.
- `collaborators`: nomes informados automaticamente no registro de empréstimo.
- `loans`: movimentações de empréstimo e devolução.

Um livro está disponível quando não existe empréstimo em `loans` com `return_date IS NULL`.
Não há tela separada para cadastrar colaboradores. No empréstimo, o operador informa o nome completo; o sistema reaproveita um colaborador existente com o mesmo nome ou cria um novo registro interno.

## Cuidados com dados reais

Quando o sistema entrar em uso, o arquivo `data/biblioteca.db` passa a conter os registros reais da biblioteca. Trate esse arquivo como dado de produção local:

- não remover;
- não sobrescrever;
- não limpar para testes;
- não commitar;
- recomendar backup periódico quando fizer sentido.

## Convenções de interface

- A tela inicial deve mostrar o estado operacional da biblioteca.
- Métricas úteis: livros cadastrados, disponíveis, emprestados e maior empréstimo em aberto.
- Tabelas devem ser legíveis e exportáveis quando fizer sentido.
- Não exigir data limite de devolução, pois o processo atual não trabalha com prazo fixo.
- Manter livros em cadastro próprio e selecionar empréstimos por lista suspensa de livros disponíveis.
- Não exigir cadastro prévio de colaborador; pedir apenas o nome completo no empréstimo.
- Seguir o Brandbook HCI como referência visual.
- Paleta principal do Brandbook:
  - azul HCI: `#182845`;
  - dourado HCI: `#E0AD55`;
  - cinza-azulado: `#5F657F`;
  - cinza claro: `#DBDBDB`;
  - branco: `#FFFFFF`.
- Tipografia de referência: Red Hat Display.
- Usar o dourado como acento, não como cor dominante.
- Preservar uma aparência corporativa, limpa e leve, com bastante branco e azul como base.

## Publicação / hospedagem (decisão pendente)

Esta seção registra o que foi decidido e o que ficou em aberto sobre publicar o
sistema. Nada de hospedagem deve ser executado sem o usuário retomar o assunto.

### Requisitos do usuário

- Publicar online para os assessores acessarem por um **link** (não manter um
  computador ligado no escritório).
- O **deploy é feito pelo próprio usuário** (sem TI).
- O **mais simples possível** e **sem custos** ($0).
- **Sem informação sensível do assessor: somente o nome.**
- Evoluir para algo mais sofisticado só quando o usuário avisar.

### Restrição técnica central

- O banco é um arquivo SQLite (`biblioteca.db`). Hosts gratuitos (incluindo o
  **Streamlit Community Cloud**) apagam o arquivo a cada reinício.
- Logo, "grátis + online + persistente" **exige um banco de dados na nuvem com
  camada gratuita**. Não há como persistir os empréstimos de graça só com o
  arquivo local no host gratuito.

### Caminho preferido (gratuito) — a confirmar

- **Host:** Streamlit Community Cloud (grátis, publica direto de um repositório
  GitHub, sem máquina ligada).
- **Acesso:** senha única compartilhada (sem cadastrar e-mail de assessor). Já
  implementado no app (ver abaixo).
- **Banco gratuito persistente:** decisão pendente entre:
  - **Turso (libSQL):** mantém o código SQLite praticamente igual (menor
    mudança). Configurar conta + URL/token nos secrets do Streamlit.
  - **Google Sheets:** os dados viram uma planilha do próprio usuário (visível e
    já servindo de backup), mas exige conta de serviço Google e uma reescrita
    maior da camada de dados.

### Opção paga (descartada por ora, mas documentada)

- **Render** com disco persistente (a partir de ~US$ 7/mês). Guardada caso o
  projeto evolua para algo mais robusto. O arquivo `render.yaml` já existe e a
  seção "Publicar online (Render)" do `README.md` descreve esse caminho pago —
  revisar/atualizar quando o caminho gratuito for escolhido.

### Residência de dados

- O usuário indicou que os dados devem ser internos. Hosts gratuitos ficam fora
  do Brasil. Se houver exigência de manter no Brasil, considerar Fly.io região
  São Paulo (`gru`) ou a nuvem da própria empresa (custo extra).

### Já implementado no código (serve para qualquer host)

- **Senha única** via `BIBLIOTECA_SENHA` (variável de ambiente **ou** secret do
  Streamlit), em `require_password()` / `get_setting()`. Sem essa variável o app
  abre direto (uso local inalterado).
- **Caminho do banco configurável** via `BIBLIOTECA_DB` (para apontar a um disco
  persistente). Default local inalterado (`data/biblioteca.db`).
- **Botão "Backup do banco (.db)"** na barra lateral.
- `render.yaml` (blueprint do Render) e `.streamlit/config.toml` (tema da marca).

### Privacidade do modelo de dados

- Guardar **somente o nome** do colaborador. As colunas `email` e `department`
  em `collaborators` existem por compatibilidade histórica, mas **não são
  coletadas nem exibidas** (ficam sempre vazias). Recomendação: removê-las das
  consultas para deixar "só o nome" literal e **não** passar a coletar dados
  sensíveis. (Ainda não feito, para não alterar comportamento agora.)

### Pendências quando retomar

1. Escolher o banco gratuito (Turso x Google Sheets).
2. Implementar a conexão escolhida (ajustar `connect_db` / camada de dados).
3. Criar o repositório no GitHub (o projeto ainda não tem commits) e conectá-lo
   ao Streamlit Community Cloud.
4. Definir a senha em `secrets` (`BIBLIOTECA_SENHA`).
5. Revisar a seção de publicação do `README.md` (hoje descreve só o Render pago).

## Git

- Antes de editar, verificar o estado do repositório com `git status --short`.
- Não reverter alterações de outras pessoas ou de outros agentes sem pedido explícito.
- Manter alterações focadas no pedido atual.
- Não incluir `data/biblioteca.db`, `__pycache__/` ou arquivos temporários no versionamento.
