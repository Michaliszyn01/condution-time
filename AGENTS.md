# Condution Time — instruções para agentes

Este arquivo vale para todo o repositório. Preserve a aplicação Flask/SQLite e
os dados pessoais do usuário.

## Exportação UFPR

- A implementação oficial fica em `scripts/export_ufpr_data.py`; o dicionário
  de dados e a linhagem ficam em `docs/ufpr_export.md`.
- A fonte desktop ativa padrão é
  `%LOCALAPPDATA%\CondutionTime\data\condution_time.db`. O banco em `instance/`
  é de desenvolvimento e não deve ser tratado como histórico atual sem uma
  solicitação explícita.
- Toda leitura do banco pessoal deve usar URI SQLite com `mode=ro` e
  `PRAGMA query_only=ON`. Não execute migrações, `db.create_all`, APIs da
  aplicação ou serviços que façam `commit` durante uma exportação.
- Não use `rebuild_study_subject_progress()` para exportar: ele regrava a tabela
  derivada. Recalcule agregados a partir de `study_records` em memória.
- Nunca edite, normalize ou deduplique o banco de origem. Registros com IDs
  distintos devem ser preservados; duplicatas exatas suspeitas são reportadas,
  não removidas silenciosamente.
- `null` significa dado desconhecido/não informado. Use zero apenas para uma
  quantidade realmente igual a zero ou ausência de linhas, acompanhada por
  `dados_registrados` quando houver risco de ambiguidade.
- Datas devem usar ISO `AAAA-MM-DD`. Os `DateTime` sem offset gravados pelo ORM
  representam UTC; exporte UTC com `Z` e horários locais com offset de
  `America/Sao_Paulo`.
- Mantenha `id_origem` em registros detalhados para validar contagens sem expor
  hashes externos. Não exporte nomes de executáveis, títulos de janela, sites,
  perfil pessoal, biometria ou outros campos fora do objetivo acadêmico.
- Se tabelas ou campos usados mudarem, atualize juntos: `REQUIRED_COLUMNS`, a
  transformação, a versão `EXPORT_SCHEMA_VERSION`, os testes e o dicionário de
  dados. Uma coluna ausente deve causar erro claro, nunca perda silenciosa.
- Arquivos gerados em `exports/ufpr/*.json` contêm dados pessoais e permanecem
  ignorados pelo Git. Não os copie para fixtures, logs, documentação ou commits.

## Validação obrigatória

Execute pelo menos:

```powershell
py -3.14 -m pytest -q tests\test_ufpr_export.py -p no:cacheprovider
py -3.14 scripts\export_ufpr_data.py
```

Antes de entregar, confira `validation_report.json`: integridade SQLite,
chaves estrangeiras, contagens, somas, IDs únicos, cobertura e duplicatas. O
status deve ser `aprovado`. Testes nunca devem apontar para o banco pessoal;
use o diretório temporário fornecido pela suíte.
