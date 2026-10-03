-- Cartão que o próprio dono usa: marca explícita, sem precisar convidar ninguém como portador.
ALTER TABLE plastico ADD COLUMN IF NOT EXISTS proprio boolean NOT NULL DEFAULT false;
GRANT UPDATE (proprio) ON plastico TO fin_app;
