---
name: Testar e editar a página do agent console
description: Como o frontend do console (template Flask único, sem build) é testado, e por que uma edição no template não aparece no preview sem restart
---

# Frontend do console: template único, sem build

A página é um só template com CSS e JS inline. Não existe bundler, nem framework, nem etapa de build — e isso é intencional: o console é infraestrutura opcional, e uma toolchain de frontend inteira para uma página seria mais coisa para quebrar do que a página.

## Teste de comportamento carrega o próprio template

O que precisa de DOM (estado "saving", erro, rollback, valores vindos da API) roda em jsdom **lendo o arquivo do template** e stubando `fetch`. Nada do JS é reescrito no teste.

**Why:** se o teste reimplementasse a lógica, ele passaria enquanto a página quebra — e é justamente rollback/erro que ninguém percebe olhando a tela em condição normal.

**How to apply:** o entrypoint continua sendo pytest (o repo é Python); ele chama o runner do Node e faz *skip* quando Node ou a dependência de DOM não está instalada, para o lado Python seguir instalável sem npm. Asserção de layout responsivo é feita sobre o texto do CSS — media query e grid — não sobre geometria renderizada, que jsdom não calcula.

## Editar o template não muda o que o preview serve

O console roda com debug desligado, então o Jinja cacheia o template no processo. Depois de mexer no HTML/CSS/JS da página é preciso **reiniciar o workflow do console** — senão o screenshot mostra a versão antiga e a divergência com o teste (que lê o arquivo do disco) parece um bug de CSS.
