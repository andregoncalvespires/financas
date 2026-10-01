-- Orçamento com vigência. Cada linha é uma "regra" de uma categoria:
--   continuo    : vale de `inicio` em diante (até `fim`, opcional)
--   ocorrencias : vale por `ocorrencias` meses seguidos a partir de `inicio`
--   meses       : vale só nos meses do ano listados em `meses` (1-12), de `inicio` em diante (até `fim`, opcional)
--   mes         : ajuste de um único mês (`inicio`); tem prioridade sobre as demais
-- Para um mês, vale a regra aplicável de `inicio` mais recente (o ajuste de um mês sempre vence).
ALTER TABLE orcamento ADD COLUMN modo text, ADD COLUMN inicio date, ADD COLUMN ocorrencias int, ADD COLUMN meses smallint[], ADD COLUMN fim date;
UPDATE orcamento SET modo = CASE WHEN mes IS NULL THEN 'continuo' ELSE 'mes' END, inicio = COALESCE(mes, DATE '2000-01-01');
ALTER TABLE orcamento ALTER COLUMN modo SET NOT NULL, ALTER COLUMN inicio SET NOT NULL;
DROP INDEX orcamento_uniq;
ALTER TABLE orcamento DROP COLUMN mes;
ALTER TABLE orcamento
  ADD CONSTRAINT orc_modo_ck CHECK (modo IN ('continuo','ocorrencias','meses','mes')),
  ADD CONSTRAINT orc_inicio_ck CHECK (inicio = date_trunc('month', inicio)::date),
  ADD CONSTRAINT orc_fim_ck CHECK (fim IS NULL OR (fim = date_trunc('month', fim)::date AND fim >= inicio)),
  ADD CONSTRAINT orc_oc_ck CHECK ((modo = 'ocorrencias') = (ocorrencias IS NOT NULL) AND (ocorrencias IS NULL OR ocorrencias BETWEEN 1 AND 240)),
  ADD CONSTRAINT orc_meses_ck CHECK ((modo = 'meses') = (meses IS NOT NULL) AND (meses IS NULL OR (cardinality(meses) BETWEEN 1 AND 12 AND meses <@ ARRAY[1,2,3,4,5,6,7,8,9,10,11,12]::smallint[]))),
  ADD CONSTRAINT orc_fim_modo_ck CHECK (fim IS NULL OR modo IN ('continuo','meses'));
CREATE UNIQUE INDEX orcamento_regra_uniq ON orcamento(categoria_id, inicio) WHERE modo <> 'mes';
CREATE UNIQUE INDEX orcamento_mes_uniq ON orcamento(categoria_id, inicio) WHERE modo = 'mes';
GRANT UPDATE (modo, inicio, ocorrencias, meses, fim) ON orcamento TO fin_app;
