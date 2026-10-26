# Condution Time

Aplicativo Flask local para acompanhamento de rotina, saúde e produtividade.
A ferramenta **Registrar** persiste registros de estudo, sono, treino,
alimentação, hidratação e uso do computador em SQLite. Os dashboards e a
pontuação usam os serviços oficiais do projeto.

## Requisitos

- Python 3.11 ou mais recente
- SQLite, incluído no Python

## Instalação no Windows

No PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edite a `SECRET_KEY` no `.env` para uso fora do desenvolvimento local. O valor
padrão de `DATABASE_URL` cria o banco em `instance/condution_time.db`.

## Migrações e execução

Com o ambiente virtual ativado:

```powershell
python -m flask --app run:app db upgrade
python -m flask --app run:app run
```

Depois, acesse `http://127.0.0.1:5000`.

Para gerar uma nova migração após alterar modelos:

```powershell
python -m flask --app run:app db migrate -m "descrição da alteração"
python -m flask --app run:app db upgrade
```

Não execute `db init` novamente: a pasta `migrations/` já pertence ao projeto.

## Testes

```powershell
python -m pytest -q
```

Os testes usam SQLite em memória e não alteram o banco local.

## Aplicativo desktop para Windows

A camada em `desktop/` inicia o mesmo Flask em `127.0.0.1`, aguarda `/health`
e abre a interface em uma janela nativa com pywebview. Ela também oferece
instância única, bandeja do sistema, encerramento coordenado e inicialização
opcional com o Windows.

Para executar durante o desenvolvimento:

```powershell
.\scripts\run_desktop.ps1
```

Argumentos aceitos pelo inicializador:

- `--background`: inicia oculto na bandeja.
- `--open`: força a abertura da janela.
- `--no-tray`: executa sem ícone na bandeja.
- `--port 5005`: usa essa porta como início da busca local.
- `--route /registrar`: abre uma rota interna permitida.

Se o executável for aberto enquanto o aplicativo já está na bandeja, a segunda
execução não cria outro servidor. Ela usa um canal IPC restrito a
`127.0.0.1`, pede para a primeira instância restaurar e focar a janela e então
termina silenciosamente. O mutex continua sendo a trava principal.

O arquivo transitório
`%LOCALAPPDATA%\CondutionTime\config\runtime.json` contém apenas PID, porta de
controle, horário e versão do protocolo. Ele é validado, removido ao sair e
substituído com segurança quando uma execução anterior terminou
inesperadamente.

As configurações do aplicativo ficam disponíveis na página **Configurações**
somente quando a interface está no modo desktop. No navegador Flask comum,
essa seção permanece visível, mas seus controles desktop ficam desabilitados.

Dados do pacote instalado não são gravados dentro de `dist/`. O aplicativo usa:

```text
%LOCALAPPDATA%\CondutionTime\
├── data\condution_time.db
├── logs\condution_time.log
├── config\desktop.json
└── backups\
```

O servidor nunca é publicado na rede: ele escuta apenas em `127.0.0.1`.

### Gerar o pacote one-folder

```powershell
.\scripts\build_windows.ps1
```

O resultado esperado é
`dist\CondutionTime\CondutionTime.exe`. Para abrir o build e seguir o checklist
manual:

```powershell
.\scripts\smoke_desktop.ps1
```

Valide: janela principal, navegação, fechar para a bandeja, executar o EXE de
novo para restaurar a mesma janela, reabrir pelo menu, início com o Windows e
**Sair**. O ícone definitivo é opcional nesta etapa;
veja `assets/README.md` para adicionar `condution_time.ico`.

### Monitoramento local do computador

No aplicativo Windows, o monitor inicia por padrão com amostras a cada 2
segundos e considera o usuário ocioso após 5 minutos sem entrada. Ele registra
somente blocos agregados com nome do executável, nome amigável, horários,
duração, classificação, categoria e contexto opcional de sessão.

- blocos consecutivos iguais são unidos;
- blocos de aplicativo abaixo de 3 segundos são descartados como ruído;
- ociosidade é salva separadamente, sem aplicativo e sem pontos;
- gaps acima de 30 segundos encerram o último bloco no último instante válido;
- blocos são divididos na meia-noite conforme `APP_TIMEZONE`;
- pausa, encerramento e mudança de sessão fecham o bloco atual;
- regras manuais valem somente para blocos novos;
- os dados ficam no SQLite de `%LOCALAPPDATA%\CondutionTime\data`.

O monitor não registra teclas, textos digitados, coordenadas do mouse,
capturas de tela, áudio, câmera, arquivos, mensagens, senhas, títulos de
janela ou URLs. Para Chrome e editores compatíveis com VS Code, o título da
janela em primeiro plano é lido apenas momentaneamente. Ele é descartado após
identificar uma assinatura permitida; nunca é gravado.

A prioridade da classificação de blocos novos é:

1. regra manual do aplicativo;
2. projeto reconhecido por regra configurada;
3. site permitido reconhecido;
4. contexto de sessão;
5. regra padrão do aplicativo;
6. fallback neutro.

`chatgpt.exe` é produtivo/estudo por padrão. `code.exe`,
`code-insiders.exe`, `cursor.exe` e `codium.exe` são
produtivos/programação. No Chrome, somente um título igual a `ChatGPT` ou que
termine com a assinatura `- ChatGPT` é reconhecido; qualquer outra aba
permanece neutra e não gera domínio, busca, URL ou título persistido.

Os comandos e consultas ficam restritos ao servidor local. O usuário pode
pausar, retomar ou desligar o monitor pela página de configurações, pela
página Uso do computador e pela bandeja.

A retenção está preparada para 90 dias, mas a exclusão automática não é
executada nesta versão. A leitura de título é limitada e pode deixar de
reconhecer uma interface após mudanças do aplicativo. Uma evolução futura
poderá usar extensão opcional, com permissão explícita e comunicação local,
enviando somente domínios permitidos por allowlist e nunca o histórico
completo. A extensão não faz parte desta versão.

### Conexão local com Saúde

A seção **Configurações > Conexão com Saúde** observa uma pasta local já
sincronizada pelo Google Drive. Não há OAuth, API do Drive ou envio externo.
São aceitos `health_connect_export.db` e ZIP contendo exatamente um banco com
esse nome.

O watcher verifica tamanho e modificação em duas observações, exige o tempo de
estabilidade configurado, testa a leitura e importa uma cópia. ZIPs são
validados contra path traversal e limites de tamanho. O banco exportado é
aberto somente para leitura.

Nesta versão são importados:

- sono principal diário, estágios e agregados de FC/SpO₂;
- sessões de exercício com distância, calorias, passos e agregados de FC;
- peso e gordura corporal;
- resumos diários de passos, distância, calorias, atividade, FC e VO₂ máx.

IDs originais e hashes normalizados permitem inserir, atualizar ou ignorar
sem duplicação. Os campos subjetivos preenchidos manualmente são preservados
ao mesclar sono ou treino. Amostras brutas de frequência cardíaca não são
copiadas para o banco principal.

O código numérico original de exercício é preservado em
`training_records.source_exercise_type`. A apresentação usa o catálogo central
de tipos do Health Connect. O SQLite exportado usa
`android.health.connect.datatypes.ExerciseSessionType` (API nativa, códigos
0–61), não as constantes de
`androidx.health.connect.client.records.ExerciseSessionRecord` (códigos
0–83). Os dois mapas ficam separados no código e nunca são intercambiados.
Assim, por exemplo, 58 é **Outro treino**, 53 é **Caminhada**, 33 é
**Corrida**, 34 é **Corrida na esteira** e 49 é **Natação em piscina**.
Um código desconhecido vira **Outro** e somente o código normalizado é escrito
no log técnico. Registros importados podem ser
selecionados no Registrar e complementados no próprio registro, sem criar uma
segunda linha.

A classificação manual de um treino importado é salva separadamente em
`manual_training_type`; o código bruto do relógio continua em
`source_exercise_type`. Reimportações atualizam somente os dados objetivos e
preservam a escolha manual. Métricas de FC, distância, calorias, velocidade e
VO₂ máx. são agregadas no intervalo da sessão quando existirem; as amostras
brutas não são duplicadas no banco principal.

Para sono que atravessa a meia-noite, `record_date` representa o dia em que a
pessoa acordou. Os estágios acordado, leve, profundo e REM mantêm seus
intervalos reais. A interface não força a soma dos estágios a coincidir com a
duração total, pois podem existir intervalos sem classificação e
arredondamentos.

O sono mais longo associado à data de despertar é marcado como principal;
outras sessões são preservadas como cochilos. “Despertares detectados” conta
somente grupos internos acordados relevantes: ignora o trecho inicial e o
despertar final, une fragmentos separados por até cinco minutos e conta grupos
com pelo menos dois minutos efetivamente acordado. “Tempo acordado” mantém a
soma separada de acordado, acordado na cama e fora da cama. A eficiência é o
tempo em estágios de sono (2, 4, 5 e 6) dividido pela duração total da sessão.
Esses números são descritivos e não constituem diagnóstico médico.

### Auditoria do export atual (29/07/2026)

A cópia auditada contém sono, estágios, treino, passos, frequência cardíaca,
oxigenação, peso, gordura corporal, metabolismo basal, VO₂ máx., distância,
velocidade e calorias. Não há registros preenchidos de hidratação, nutrição,
frequência cardíaca de repouso, HRV, temperatura da pele, massa magra, água
corporal, elevação, rota GPS, voltas ou segmentos de exercício. A interface não
cria cartões nem valores para métricas ausentes.

### Perfil e evolução

`/perfil` é a visão histórica, separada da Home diária. Ela oferece períodos
de 7, 30 e 90 dias, 6 meses, 1 ano ou todo o histórico, com estudos, saúde,
treinos, sono, computador, conquistas e metas.

O nível de cada matéria continua sendo recalculável pelo histórico de estudo.
O nível geral usa o ledger `experience_events`, com `event_key` único:
sessão concluída vale 10 XP, estudo válido 5 XP, treino completo 5 XP, sono
subjetivo completo 3 XP e dia 5/5 vale 15 XP. Há limites diários por tipo; abrir
páginas, editar um registro ou importar o mesmo dado não concede XP novamente.
Conquistas são idempotentes e concedem o XP definido no catálogo.

Para avançar no nível geral, o custo é
`100 + (nível - 1) * 50` XP. O total e o nível podem ser reconstruídos
integralmente pelo ledger e nunca alteram a pontuação diária oficial.

### Registros e consultas por data

Estudo, treino, sono, refeição e hidratação aceitam hoje ou uma data anterior;
datas futuras são rejeitadas no serviço. Estudo, Treino, Sono e Computador
aceitam `?date=AAAA-MM-DD`, mantêm a seleção na URL e oferecem dia anterior,
próximo dia e retorno para hoje. Um registro antigo atualiza Histórico, Perfil
e calendário daquela data sem mudar o resumo da Home atual.

## Configuração

As variáveis aceitas são:

- `FLASK_APP`: entrada do Flask; use `run:app`.
- `FLASK_ENV`: ambiente local.
- `SECRET_KEY`: chave da aplicação.
- `DATABASE_URL`: conexão do SQLAlchemy. O padrão é
  `sqlite:///condution_time.db`, resolvido dentro de `instance/`.

Uma futura conexão PostgreSQL pode ser definida em `DATABASE_URL` sem alterar
os modelos ou a camada de serviço.

## Arquitetura

- `app/config.py`: configuração por ambiente.
- `app/extensions.py`: instâncias de SQLAlchemy e Flask-Migrate.
- `app/models/`: modelos persistentes e mixins de campos comuns.
- `app/services/record_service.py`: validação, conversões, transações e
  consultas reutilizáveis.
- `app/api/records.py`: endpoints JSON da ferramenta Registrar.
- `migrations/`: histórico versionado do esquema.
- `tests/`: testes isolados com SQLite em memória.
- `desktop/`: janela, servidor local, bandeja, configuração e integração Windows.
- `desktop/monitoring/`: captura, ociosidade, classificação, agregação e agente.
- `app/health_import/`: validação, leitura, mapeamento, upsert e watcher local.
- `app/services/profile_service.py`: métricas históricas, comparação e XP.
- `CondutionTime.spec`: empacotamento PyInstaller one-folder.

O banco local, ambientes virtuais, caches e logs são ignorados pelo Git.
