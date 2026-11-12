# Feeds de Vagas (RSS)

Gera feeds RSS das vagas de: Unimed Alto Vale, SC Treinamentos, Portal da Inclusão SESI SC,
FIESC (Rio do Sul, PcD), PCI Concursos (Rio do Sul), CIEE SC (Gupy) e Sesc SC (Rio do Sul).

## Como publicar no GitHub (grátis, link permanente)

1. Crie um repositório **público** chamado `vagas-rss` em https://github.com/new
2. Envie esta pasta inteira para ele (inclusive `.github/workflows/update.yml`).
3. Em **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, pasta `/docs`.
4. Em **Actions**, abra "Atualizar feeds" e clique em **Run workflow** uma vez.
5. Assine no Feedly: `https://SEU-USUARIO.github.io/vagas-rss/feed.xml`

A coleta roda sozinha a cada 3 horas. Cada execução salva uma alteração, e isso mantém o
agendamento ativo: o GitHub desliga agendamentos de repositórios parados há 60 dias.

Feeds por fonte: `unimed.xml`, `sctreinamentos.xml`, `sesisc.xml`, `fiesc.xml`, `pci.xml`,
`cieesc.xml`, `sesc.xml`.
