-- 008: meses "pulados" de uma recorrência. Excluir uma ocorrência (previsto ou já efetivado) registra o mês aqui,
-- e a geração automática de previstos deixa de recriá-lo. Os demais meses da recorrência seguem normais.
CREATE TABLE recorrencia_pulada (
  recorrencia_id uuid NOT NULL REFERENCES recorrencia(id) ON DELETE CASCADE,
  mes date NOT NULL CHECK (mes = date_trunc('month', mes)::date),   -- sempre o dia 1
  criado_por uuid REFERENCES usuario(id) ON DELETE SET NULL,
  criado_em timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (recorrencia_id, mes)
);

ALTER TABLE recorrencia_pulada ENABLE ROW LEVEL SECURITY;
-- vê quem vê a recorrência; marca e desfaz quem pode editá-la (a subconsulta passa pela RLS de recorrencia)
CREATE POLICY recp_sel ON recorrencia_pulada FOR SELECT
  USING (EXISTS (SELECT 1 FROM recorrencia r WHERE r.id = recorrencia_id));
CREATE POLICY recp_ins ON recorrencia_pulada FOR INSERT
  WITH CHECK (EXISTS (SELECT 1 FROM recorrencia r WHERE r.id = recorrencia_id AND pode_editar_alvo(r.conta_id, r.plastico_id, r.criado_por)));
CREATE POLICY recp_del ON recorrencia_pulada FOR DELETE
  USING (EXISTS (SELECT 1 FROM recorrencia r WHERE r.id = recorrencia_id AND pode_editar_alvo(r.conta_id, r.plastico_id, r.criado_por)));
GRANT SELECT, INSERT, DELETE ON recorrencia_pulada TO fin_app;
