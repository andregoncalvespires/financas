-- Mês de competência da recorrência em relação ao mês do caixa: -1 (anterior), 0 (mesmo mês), 1 (seguinte).
-- Quando diferente de 0, a competência é o dia 1 do mês escolhido e o caixa continua no dia da recorrência.
ALTER TABLE recorrencia ADD COLUMN IF NOT EXISTS competencia_mes smallint NOT NULL DEFAULT 0 CHECK (competencia_mes IN (-1, 0, 1));
GRANT UPDATE (competencia_mes) ON recorrencia TO fin_app;
