# Exportação UFPR do Condution Time

## Finalidade e artefatos

Esta exportação transforma somente os dados do Condution Time úteis para
analisar preparação acadêmica, rotina, sono, estudo, desempenho, consistência,
foco e distração. A fonte original nunca é alterada.

Arquivos envolvidos:

- `scripts/export_ufpr_data.py`: exportador independente, somente leitura;
- `exports/ufpr/condution_time_ufpr.json`: arquivo principal para enviar ao
  projeto do ChatGPT;
- `exports/ufpr/validation_report.json`: prova de integridade, contagens, somas,
  duplicatas e ausências;
- `tests/test_ufpr_export.py`: testes com banco temporário, sem acesso ao banco
  pessoal;
- `AGENTS.md`: regras para futuras alterações.

Os dois JSONs gerados são ignorados pelo Git porque contêm dados pessoais.

## Arquitetura auditada

O sistema é uma aplicação Flask com SQLAlchemy, Flask-Migrate/Alembic e SQLite.
Os modelos ficam em `app/models`, as regras de cálculo em `app/services`, as
APIs em `app/api`, as páginas em `app/routes.py` e o empacotamento desktop em
`desktop`.

Há duas localizações de banco com papéis diferentes:

| Local | Papel |
| --- | --- |
| `%LOCALAPPDATA%\CondutionTime\data\condution_time.db` | Banco ativo da aplicação desktop e fonte padrão da exportação. |
| `instance\condution_time.db` | Banco de desenvolvimento Flask; no inventário atual é menor e mais antigo, portanto não é usado por padrão. |

`desktop/paths.py` resolve o banco desktop. `app/config.py` mantém
`sqlite:///condution_time.db` como padrão do modo Flask. O exportador replica
apenas a resolução do caminho; ele não importa `desktop.paths`, pois as funções
desse módulo podem criar diretórios.

O esquema é versionado em `migrations/versions`. Na validação de 19/08/2026, o
banco ativo estava na revisão `e6b9c3d7f204` e `PRAGMA integrity_check`
retornou `ok`.

### Modelos e tabelas relevantes

| Modelo | Tabela | Uso na exportação |
| --- | --- | --- |
| `StudyRecord` | `study_records` | Matéria, assunto, duração, questões, acertos, foco, aprendizado, dificuldade e origem. |
| `SessionRecord` | `session_records` | Sessões cronometradas, objetivo, duração real, foco, produtividade, distração e reflexão. |
| `SleepRecord` | `sleep_records` | Horários, duração, sono principal/cochilo, qualidade percebida, despertares e descanso. |
| `ComputerActivityBlock` | `computer_activity_blocks` | Intervalos agregados produtivos, distraídos e ociosos, além dos totais diários. |
| `UserProfile` | `user_profile` | Objetivo acadêmico, meta semanal de estudo e meta de sono. |

`StudySubjectProgress`/`study_subject_progress` é um cache derivado. Ele não é
fonte da exportação: `rebuild_study_subject_progress()` recalcula e faz
`commit`, o que seria incompatível com uma leitura segura. O desempenho por
matéria é recalculado em memória diretamente de `study_records`.

### Serviços e APIs existentes

- `app/services/study_service.py` fornece resumo diário, semana, calendário,
  distribuição por matéria e pontuação provisória.
- `app/services/session_service.py` controla o ciclo das sessões e serializa
  suas métricas.
- `app/services/computer_service.py` agrega blocos e calcula os totais de uso.
- `app/services/profile_service.py` e `profile_page_service.py` produzem
  evolução e metas; parte dessas rotinas pode persistir estado derivado.
- `app/services/scoring_service.py` calcula a pontuação oficial da aplicação,
  que mistura estudo, treino, sono, nutrição, computador e bônus de sessão.

As APIs relevantes são `/api/records/study`,
`/api/records/<tipo>/<id>`, `/api/records/counts`, `/api/sessions`,
`/api/profile/study`, `/api/profile/goals`, `/api/profile/comparison` e
`/api/computer-monitor/today-summary`. Elas atendem a interface; não existia
uma API ou um arquivo de exportação acadêmica consolidada. O novo fluxo é um
script local para não ampliar a superfície HTTP nem alterar o aplicativo.

Os scripts anteriores em `scripts` tratam migração, diagnóstico, importação do
Health Connect, auditoria e build. Nenhum deles reunia estudo, sono e computador
para o objetivo UFPR.

## Execução

No PowerShell, a partir da raiz do projeto:

```powershell
py -3.14 scripts\export_ufpr_data.py
```

Para usar caminhos explícitos:

```powershell
py -3.14 scripts\export_ufpr_data.py `
  --database "C:\caminho\condution_time.db" `
  --output "C:\caminho\condution_time_ufpr.json" `
  --validation-output "C:\caminho\validation_report.json"
```

O comando retorna código `0` somente se a validação for aprovada, `1` para
erro de leitura/esquema e `2` para uma exportação criada mas reprovada pela
validação.

## Linhagem e transformações

| Seção final | Fonte | Transformação |
| --- | --- | --- |
| `metas` | `user_profile` / `UserProfile` | Seleciona determinadamente o menor `id`; texto vazio vira `null`. Nome, nascimento e metas não acadêmicas são omitidos. |
| `sessoes_estudo` | `study_records` / `StudyRecord` | Preserva uma linha por `id`; limpa espaços externos, cria chave de matéria, calcula erros e taxa de acerto. |
| `sessoes_foco` | `session_records` / `SessionRecord` | Preserva uma linha por `id`; converte segundos também para minutos e exporta UTC e horário local. |
| `sessoes_sono` | `sleep_records` / `SleepRecord` | Preserva sono principal e cochilos; converte instantes UTC para `America/Sao_Paulo`; não exporta biometria. |
| `periodos_computador` | `computer_activity_blocks` / `ComputerActivityBlock` | Preserva por `id` apenas blocos produtivos, distraídos ou ociosos; remove nomes de aplicativos, projetos e sites. |
| `resumos_diarios` | As quatro tabelas acima | Cria uma série diária contínua entre a primeira e a última data de qualquer fonte relevante. Ausência é marcada por `dados_registrados=false`. |
| `resumos_semanais` | `resumos_diarios` e meta do perfil | Agrega segunda a domingo desde o primeiro estudo registrado; calcula progresso da meta somente quando ela existe. |
| `desempenho_por_materia` | `study_records` | Agrupa matéria após remover espaços repetidos e aplicar `casefold`; não usa o cache persistido. |
| `consistencia_estudo` | Datas distintas de `study_records` | Calcula proporção de dias estudados, maior sequência e sequência no fim do período. |
| `qualidade_dados` | Consultas somente leitura | Registra ausências, duplicatas suspeitas, inconsistências semânticas, quantidade de perfis e resultado da validação. |

Regras importantes:

- `erros = questões_com_resultado - acertos`;
- a taxa de acerto usa apenas registros em que `correct_answers` existe;
- taxa com denominador zero é `null`, não `0`;
- o foco qualitativo usa a referência já adotada pelo dashboard:
  `low=20`, `regular=40`, `good=60`, `very_good=80`, `excellent=100`;
- o foco diário e por matéria é a média simples dessas referências por registro;
- o foco do computador é
  `produtivo / (produtivo + distraído)`, igual ao denominador do serviço atual;
- o total de sono inclui todas as sessões do dia de despertar; cochilos ficam
  separados do sono principal;
- datetimes sem offset no SQLite são tratados como UTC porque os modelos,
  importador e monitor os gravam a partir de instantes UTC;
- o JSON usa datas ISO `AAAA-MM-DD`, UTC com sufixo `Z` e horário local com
  offset explícito.

## Dicionário de dados

### Raiz e metadados

| Campo | Significado |
| --- | --- |
| `metadados` | Proveniência e contrato do arquivo. |
| `metas` | Metas acadêmicas e de sono do perfil. |
| `sessoes_estudo` | Registros detalhados de estudo. |
| `sessoes_foco` | Sessões cronometradas detalhadas. |
| `sessoes_sono` | Sessões de sono detalhadas. |
| `periodos_computador` | Intervalos produtivos, distraídos ou ociosos sem identificação do aplicativo. |
| `resumos_diarios` | Série contínua para relacionar rotina e desempenho. |
| `resumos_semanais` | Evolução semanal e progresso de meta. |
| `desempenho_por_materia` | Totais e desempenho agrupados por matéria. |
| `consistencia_estudo` | Indicadores de regularidade. |
| `qualidade_dados` | Resultado resumido da auditoria. |
| `metadados.schema_exportacao` | Versão do contrato JSON. |
| `metadados.gerado_em_utc` | Instante em que o snapshot foi gerado. |
| `metadados.fuso_horario_local` | Fuso usado nas conversões locais. |
| `metadados.fonte` | Descrição lógica da fonte, sem caminho pessoal. |
| `metadados.versao_migracao_fonte` | Revisão Alembic lida de `alembic_version`. |
| `metadados.cobertura_fontes.<dominio>.primeira_data` | Primeira `record_date` disponível no domínio; `null` se vazio. |
| `metadados.cobertura_fontes.<dominio>.ultima_data` | Última `record_date` disponível no domínio; `null` se vazio. |
| `metadados.cobertura_fontes.<dominio>.linhas` | Quantidade de linhas na tabela de origem. |
| `metadados.politica_valores_ausentes` | Regra textual para interpretar `null`, zero e `dados_registrados`. |

### `metas`

| Campo | Significado |
| --- | --- |
| `id_perfil_origem` | ID técnico do perfil usado para rastreabilidade. |
| `objetivo_academico` | Texto de `academic_goal`; `null` quando não preenchido. |
| `meta_estudo_semanal_minutos` | Meta semanal persistida; `null` quando ausente. |
| `meta_sono_por_noite_minutos` | Meta persistida de sono por noite. |

### Item de `sessoes_estudo`

| Campo | Significado |
| --- | --- |
| `id_origem` | Chave primária de `study_records`; impede duplicação introduzida pela exportação. |
| `data` | Dia acadêmico informado pelo usuário. |
| `materia` | Nome exibível, com espaços normalizados. |
| `materia_chave` | Nome normalizado por espaços e caixa para agrupamento. |
| `assunto` | Tópico estudado. |
| `duracao_minutos` | Duração persistida da sessão. |
| `questoes_resolvidas` | `questions_count`; pode ser `null`. |
| `acertos` | `correct_answers`; pode ser `null`. |
| `erros` | Diferença entre questões e acertos; `null` se o resultado não existe. |
| `taxa_acerto_percentual` | Acertos dividido por questões; `null` sem denominador. |
| `qualidade_foco_codigo` | Código persistido (`low` a `excellent`). |
| `qualidade_foco` | Rótulo em português do código. |
| `foco_percentual_referencia` | Escala ordinal de referência do dashboard; não é medição instrumental. |
| `o_que_aprendeu` | Texto livre de aprendizado; vazio vira `null`. |
| `dificuldade_encontrada` | Texto livre de dificuldade; vazio vira `null`. |
| `origem_registro` | Origem persistida, como `manual` ou `monitored_session`. |
| `registrado_em_utc` | Momento em que a linha foi salva; não representa necessariamente o início do estudo. |

### Item de `sessoes_foco`

| Campo | Significado |
| --- | --- |
| `id_origem`, `data` | ID da linha e dia local da sessão. |
| `tipo_sessao` | Tipo persistido, por exemplo `study`, `computer` ou `project`. |
| `titulo` | Título configurado pelo usuário. |
| `categoria_relacionada` | Categoria validada pelo serviço de sessão. |
| `duracao_alvo_minutos` | Duração planejada; pode ser `null`. |
| `duracao_real_segundos`, `duracao_real_minutos` | Mesma duração real em unidade exata e unidade amigável. |
| `monitoramento_computador_ativo` | Indica se a sessão solicitou monitoramento local. |
| `objetivo`, `resultado`, `aprendizado`, `dificuldade` | Textos de planejamento e reflexão; vazios viram `null`. |
| `autoavaliacao_1_a_10` | Nota opcional validada entre 1 e 10. |
| `foco_percentual` | Percentual opcional persistido ao concluir. |
| `tempo_produtivo_segundos`, `tempo_distraido_segundos` | Totais persistidos da sessão. |
| `status` | Estado (`running`, `paused`, `completed` ou `cancelled`). |
| `inicio_utc`, `fim_utc` | Instantes UTC padronizados. |
| `inicio_local`, `fim_local` | Os mesmos instantes no fuso local. |

### Item de `sessoes_sono`

| Campo | Significado |
| --- | --- |
| `id_origem` | Chave primária de `sleep_records`. |
| `data_despertar` | `record_date`; por contrato do importador é o dia em que a pessoa acordou. |
| `principal` | Distingue o sono principal dos cochilos. |
| `inicio_horario_registrado`, `fim_horario_registrado` | Campos `Time` originais no formato `HH:MM`. |
| `inicio_local`, `fim_local` | Instantes absolutos convertidos ao fuso local; podem ser `null` em registros manuais antigos. |
| `duracao_minutos`, `duracao_horas` | Duração persistida em duas unidades. |
| `qualidade_percebida_codigo`, `qualidade_percebida` | Valor subjetivo original e rótulo; ambos podem ser `null`. |
| `despertares` | Contagem persistida de despertares. |
| `acordou_descansado_codigo`, `acordou_descansado` | Resposta subjetiva e rótulo; podem ser `null`. |
| `observacoes` | Nota de sono, quando preenchida. |
| `origem_registro` | Origem manual, importada ou mesclada. |

### Item de `periodos_computador`

| Campo | Significado |
| --- | --- |
| `id_origem`, `data` | ID de `computer_activity_blocks` e dia local do bloco. |
| `tipo_periodo` | `foco_produtivo`, `distracao` ou `ocioso`. |
| `classificacao` | Classificação persistida; um bloco ocioso pode ter classificação técnica `ignored`. |
| `categoria` | Categoria ampla, como `study`, `programming`, `social` ou `gaming`. |
| `inicio_local`, `fim_local` | Limites do bloco no fuso local. |
| `duracao_segundos`, `duracao_minutos` | Duração exata e conversão amigável. |
| `origem_classificacao` | Regra que classificou o bloco, sem conteúdo da janela. |
| `id_sessao_foco` | FK para `sessoes_foco.id_origem`; `null` sem vínculo. |

### Item de `resumos_diarios`

| Campo | Significado |
| --- | --- |
| `data` | Dia contínuo da série. |
| `dia_semana_iso` | Segunda=1 até domingo=7. |
| `estudo.dados_registrados` | Existência de ao menos um `StudyRecord` no dia. |
| `estudo.tempo_total_minutos`, `tempo_total_horas` | Soma das durações de estudo. |
| `estudo.sessoes` | Quantidade de registros de estudo. |
| `estudo.materias` | Matérias distintas normalizadas. |
| `estudo.questoes_registradas` | Soma de todas as questões informadas. |
| `estudo.questoes_com_resultado` | Questões dos registros que também têm acertos. |
| `estudo.acertos`, `estudo.erros`, `estudo.taxa_acerto_percentual` | Resultado agregado somente sobre questões com resultado. |
| `estudo.foco_medio_percentual_referencia` | Média simples da escala ordinal de foco. |
| `sono.dados_registrados` | Existência de qualquer sessão de sono associada ao dia. |
| `sono.sessoes_sono`, `sono.sessoes_principais` | Quantidades total e principal. |
| `sono.tempo_total_minutos`, `sono.tempo_total_horas` | Sono principal mais cochilos. |
| `sono.sono_principal_minutos`, `sono.cochilos_minutos` | Separação entre sono principal e cochilos. |
| `sono.inicio_sono_principal_local`, `sono.fim_sono_principal_local` | Intervalo absoluto do sono principal. |
| `sono.qualidade_percebida_codigo`, `sono.qualidade_percebida` | Qualidade subjetiva principal. |
| `sono.despertares_sono_principal` | Despertares do sono principal. |
| `sono.acordou_descansado_codigo`, `sono.acordou_descansado` | Descanso subjetivo principal. |
| `sessoes_foco.dados_registrados` | Existência de qualquer `SessionRecord`. |
| `sessoes_foco.sessoes_totais`, `sessoes_concluidas` | Contagens por qualquer status e por status concluído. |
| `sessoes_foco.duracao_concluida_segundos` | Soma somente de sessões concluídas. |
| `sessoes_foco.foco_medio_percentual` | Média de foco das concluídas que possuem o campo. |
| `sessoes_foco.tempo_produtivo_segundos`, `tempo_distraido_segundos` | Totais das sessões concluídas. |
| `computador.dados_registrados` | Existência de blocos do monitor no dia. |
| `computador.tempo_produtivo_segundos`, `tempo_distraido_segundos`, `tempo_neutro_segundos`, `tempo_ocioso_segundos`, `tempo_ignorado_segundos` | Soma por classificação/ociosidade. |
| `computador.taxa_foco_percentual` | Produtivo sobre produtivo + distraído; `null` sem tempo classificado. |
| `computador.categoria_estudo_total_segundos` | Todo tempo não ignorado classificado na categoria `study`. |
| `computador.categoria_estudo_produtivo_segundos`, `categoria_estudo_distraido_segundos` | Partes produtiva e distraída da categoria `study`. |

### Item de `resumos_semanais`

| Campo | Significado |
| --- | --- |
| `ano_iso`, `semana_iso` | Identificação ISO da semana. |
| `inicio_semana`, `fim_semana` | Segunda e domingo completos. |
| `periodo_observado_inicio`, `periodo_observado_fim` | Trecho realmente coberto na primeira/última semana. |
| `estudo.dados_registrados`, `tempo_total_minutos`, `sessoes`, `dias_com_estudo` | Presença e volume semanal. |
| `estudo.questoes_registradas`, `questoes_com_resultado`, `acertos`, `erros`, `taxa_acerto_percentual` | Desempenho semanal com a mesma política diária. |
| `estudo.meta_semanal_minutos` | Meta persistida no perfil. |
| `estudo.progresso_meta_percentual` | Tempo dividido pela meta; pode superar 100%. |
| `estudo.meta_cumprida` | Booleano ou `null` quando não há meta. |
| `sono.dias_com_registro` | Dias da semana com sono registrado. |
| `sono.media_horas_por_dia_registrado` | Média somente entre dias que têm sono; não trata ausência como zero. |
| `computador.tempo_produtivo_segundos`, `tempo_distraido_segundos` | Totais semanais globais. |
| `computador.categoria_estudo_total_segundos` | Total semanal na categoria de estudo. |

### `desempenho_por_materia`, consistência e qualidade

| Campo | Significado |
| --- | --- |
| `desempenho_por_materia[].materia`, `materia_chave` | Nome exibível e chave de agrupamento. |
| `primeira_data_estudo`, `ultima_data_estudo` | Limites dos registros daquela matéria. |
| `dias_com_estudo`, `sessoes`, `tempo_total_minutos` | Consistência e volume por matéria. |
| `questoes_registradas`, `questoes_com_resultado`, `acertos`, `erros`, `taxa_acerto_percentual` | Desempenho agregado por matéria. |
| `foco_medio_percentual_referencia` | Média da referência ordinal de foco. |
| `consistencia_estudo.inicio_periodo_observado` | Primeiro dia com estudo. |
| `consistencia_estudo.fim_periodo_observado` | Último dia de qualquer fonte relevante no snapshot. |
| `dias_calendario_observados`, `dias_com_estudo`, `taxa_dias_com_estudo_percentual` | Denominador, numerador e proporção de consistência. |
| `maior_sequencia_dias` | Maior sequência de dias consecutivos com estudo. |
| `sequencia_no_fim_do_periodo_dias` | Sequência que alcança o último dia do snapshot; será zero se o último dia não tiver estudo. |
| `ultima_data_com_estudo` | Último registro acadêmico. |
| `semanas_com_meta_cumprida` | Quantidade de semanas aprovadas; `null` sem meta. |
| `qualidade_dados.status_validacao` | `aprovado` ou `reprovado`. |
| `duplicatas_suspeitas_na_fonte.<dominio>.grupos` | Grupos com mesmos campos de negócio. |
| `duplicatas_suspeitas_na_fonte.<dominio>.linhas_excedentes` | Linhas além da primeira dentro desses grupos; não são removidas. |
| `sono_ids_fonte_repetidos` | IDs externos de sono repetidos. |
| `datas_com_multiplos_sonos_principais` | Datas que violam a expectativa de um sono principal. |
| `qualidade_dados.valores_ausentes.<indicador>` | Contagem explícita para cada campo relevante auditado. |
| `qualidade_dados.inconsistencias_semanticas.<indicador>` | Quantidade de linhas que violam faixas, sinais, ordem temporal ou taxonomias esperadas. |
| `perfis_encontrados`, `perfil_utilizado` | Quantidade de perfis e regra determinística de seleção. |

O relatório de validação acrescenta `integridade_sqlite`,
`problemas_chaves_estrangeiras`, uma lista de `verificacoes` com
`valor_fonte`/`valor_exportado`, `aviso_duplicatas`, `linhas_exportadas`, a lista
`dados_omitidos_por_escopo`, o nome do arquivo e `sha256_exportacao`.

## Validação do snapshot atual

O arquivo gerado em 19/08/2026 foi aprovado com:

- 4 registros de estudo, 267 minutos, 20 questões e 19 acertos;
- 125 sessões de sono;
- 0 sessões cronometradas em `session_records`;
- 3.180 blocos de computador na fonte e 1.386 períodos detalhados
  produtivos/distraídos/ociosos no arquivo;
- 113 dias contínuos de resumo e 4 resumos semanais;
- nenhuma duplicata exata suspeita nos domínios auditados;
- nenhuma FK quebrada e IDs exportados únicos;
- 124 sessões de sono sem qualidade percebida e sem resposta sobre descanso,
  coerentes com registros importados que não receberam complemento subjetivo.

As contagens e o hash do arquivo ficam no relatório e mudam quando o monitor ou
o usuário adicionam dados. A cobertura verificada no snapshot foi:

| Domínio | Primeira data | Última data |
| --- | --- | --- |
| Estudo | 28/07/2026 | 12/08/2026 |
| Sono | 29/04/2026 | 18/08/2026 |
| Sessões de foco | sem registros | sem registros |
| Computador | 28/07/2026 | 19/08/2026 |

## Dados não exportados

- `training_records`, `meal_records`, `hydration_records`, medidas corporais e
  métricas cardiovasculares: fora do objetivo acadêmico desta etapa;
- `daily_health_summaries`: passos, calorias, distância, FC e VO₂ máx. não são
  necessários para as perguntas definidas;
- estágios de sono, FC e SpO₂: biometria detalhada não solicitada;
- nome, avatar, nascimento, altura e objetivo físico do perfil;
- `study_subject_progress`: cache derivado e potencialmente regravável;
- pontuação diária oficial: combina cinco domínios não acadêmicos e não é um
  fato persistido simples;
- XP, conquistas, notificações, regras, logs e histórico de importação;
- nomes de executáveis, nomes amigáveis, projetos, sites e identificadores do
  Health Connect;
- blocos individuais neutros ou ignorados. Seus totais diários continuam no
  resumo para não distorcer a cobertura, mas seu detalhamento seria ruído.

## Limitações

1. `study_records` não possui início/fim real do estudo. `created_at` é horário
   de salvamento, portanto `registrado_em_utc` não deve ser interpretado como
   horário da sessão.
2. No snapshot atual não há linhas em `session_records`; a estrutura está pronta
   para dados futuros, mas não pode preencher foco cronometrado retroativamente.
3. O objetivo acadêmico e a meta semanal podem estar `null`; o exportador não
   cria metas que o usuário não registrou.
4. “Erros” e taxas são derivados de questões/acertos. Não existe um campo de
   erro independente no modelo.
5. A escala de foco qualitativo é uma referência ordinal do sistema, não uma
   medição objetiva.
6. Classificações do computador são heurísticas baseadas em regras. Elas ajudam
   a comparar períodos, mas não revelam o conteúdo real da atividade.
7. Ausência de dados não prova ausência de estudo ou sono. Os sinalizadores
   `dados_registrados` devem acompanhar qualquer interpretação.
8. Correlação entre sono, distração e desempenho não implica causalidade.
9. A exportação é um snapshot. O monitor pode gravar novos blocos depois da
   geração; execute novamente antes de enviar uma versão atualizada.
10. Linhas distintas nunca são apagadas por parecerem iguais. Possíveis
    duplicatas são informadas para revisão humana, preservando o histórico.

## Exemplo ilustrativo

O recorte abaixo usa valores fictícios e mostra a forma das principais seções:

```json
{
  "metadados": {
    "schema_exportacao": "1.0.0",
    "gerado_em_utc": "2026-08-19T17:00:00Z",
    "fuso_horario_local": "America/Sao_Paulo"
  },
  "metas": {
    "id_perfil_origem": 1,
    "objetivo_academico": "Aprovação na UFPR",
    "meta_estudo_semanal_minutos": 600,
    "meta_sono_por_noite_minutos": 480
  },
  "sessoes_estudo": [
    {
      "id_origem": 101,
      "data": "2026-08-18",
      "materia": "Matemática",
      "materia_chave": "matemática",
      "assunto": "Funções",
      "duracao_minutos": 90,
      "questoes_resolvidas": 20,
      "acertos": 15,
      "erros": 5,
      "taxa_acerto_percentual": 75.0,
      "qualidade_foco_codigo": "good",
      "qualidade_foco": "bom",
      "foco_percentual_referencia": 60
    }
  ],
  "resumos_diarios": [
    {
      "data": "2026-08-18",
      "dia_semana_iso": 2,
      "estudo": {
        "dados_registrados": true,
        "tempo_total_minutos": 90,
        "questoes_com_resultado": 20,
        "acertos": 15,
        "erros": 5,
        "taxa_acerto_percentual": 75.0
      },
      "sono": {
        "dados_registrados": true,
        "tempo_total_horas": 7.75
      },
      "computador": {
        "dados_registrados": true,
        "tempo_produtivo_segundos": 5400,
        "tempo_distraido_segundos": 1200,
        "taxa_foco_percentual": 81.82
      }
    }
  ]
}
```
