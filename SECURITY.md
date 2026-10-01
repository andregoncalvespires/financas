# Segurança · Security · Segurança (PT)

## Português (Brasil)

**Como relatar uma vulnerabilidade:** não abra uma issue pública. Use "Report a vulnerability" na aba *Security* deste repositório no GitHub (relato privado). Descreva o problema, como reproduzi-lo e a versão afetada. Respondemos assim que possível.

**Versões com correções:** a versão principal mais recente (imagem `ghcr.io/andregoncalvespires/financas:1`). Mantenha o aplicativo atualizado.

**Boas práticas de quem instala:** não publique a porta 8000 diretamente na internet (use HTTPS por túnel ou proxy), proteja o `docker-compose.yml` (ele guarda a senha do SMTP) e os backups, use senha de app (e não a senha principal) no SMTP e revogue chaves que tenham sido expostas.

## Português (Portugal)

**Como comunicar uma vulnerabilidade:** não abra uma issue pública. Use "Report a vulnerability" no separador *Security* deste repositório no GitHub (comunicação privada). Descreva o problema, como o reproduzir e a versão afetada.

**Versões com correções:** a versão principal mais recente (imagem `ghcr.io/andregoncalvespires/financas:1`).

**Boas práticas para quem instala:** não publique a porta 8000 diretamente na internet (use HTTPS através de túnel ou proxy), proteja o `docker-compose.yml` (guarda a palavra-passe do SMTP) e as cópias de segurança, use palavra-passe de aplicação (e não a principal) no SMTP e revogue chaves que tenham sido expostas.

## English

**Reporting a vulnerability:** please do not open a public issue. Use "Report a vulnerability" under this repository's *Security* tab on GitHub (private report). Describe the problem, how to reproduce it and the affected version.

**Supported versions:** the latest major version (image `ghcr.io/andregoncalvespires/financas:1`).

**Good practice for installers:** do not publish port 8000 directly to the internet (use HTTPS through a tunnel or proxy), protect `docker-compose.yml` (it holds the SMTP password) and your backups, use an app password (not your main password) for SMTP, and revoke any key that has been exposed.
