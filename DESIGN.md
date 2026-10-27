---
version: alpha
name: AI-продюсер YouTube-канала — страница-витрина
description: Светлая, спокойная и дружелюбная страница для авторов YouTube-каналов про нейросети; один зелёный акцент, крупные заголовки, мягкое скругление.
colors:
  background: "#FBFDFB"
  surface: "#FFFFFF"
  foreground: "#1D2A24"
  muted: "#566860"
  border: "#D9E6DE"
  primary: "#007A50"
  primary-hover: "#00633F"
  on-primary: "#FFFFFF"
  primary-tint: "#E4F3EA"
typography:
  h1:
    fontFamily: Onest
    fontSize: 3.25rem
    fontWeight: 800
    lineHeight: 1.1
  h2:
    fontFamily: Onest
    fontSize: 2rem
    fontWeight: 800
    lineHeight: 1.2
  body:
    fontFamily: Onest
    fontSize: 1.125rem
    fontWeight: 400
    lineHeight: 1.6
  small:
    fontFamily: Onest
    fontSize: 0.9rem
    fontWeight: 400
    lineHeight: 1.5
  button:
    fontFamily: Onest
    fontSize: 1.125rem
    fontWeight: 800
    lineHeight: 1.2
rounded:
  sm: 0.5rem
  md: 0.75rem
  lg: 1rem
spacing:
  sm: 0.5rem
  md: 1rem
  lg: 2rem
  xl: 4rem
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.button}"
    rounded: "{rounded.md}"
    padding: 0.875rem
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.lg}"
    padding: 1.5rem
  note:
    backgroundColor: "{colors.primary-tint}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 1rem
  caption:
    backgroundColor: "{colors.background}"
    textColor: "{colors.muted}"
    typography: "{typography.small}"
  code-block:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.md}"
    padding: 1rem
  divider:
    backgroundColor: "{colors.border}"
    height: 1px
---

## Overview

Спокойная, свежая и разговорная страница: много воздуха, один зелёный акцент, крупные заголовки, текст без жаргона. Читатель — SMM-специалист или автор канала, не технарь, поэтому главное — понять за несколько секунд, что это и как начать.

Источник: выбор из трёх вариантов по просьбе «светлый, спокойный, дружелюбный, один яркий акцент, бесплатные шрифты с кириллицей»; итог — вариант 1, джейд + Onest (рекомендованный; сначала был выбран янтарный + Nunito, затем человек сменил решение). Готовых галерей тем у Pico нет, поэтому значения заданы переменными `--pico-*` поверх стандартной темы. Основа акцента — цветовая тема Pico `jade`, но её `#00B478` слишком светлый для текста на белом, поэтому взят более тёмный `#007A50` (5,4:1; норма 4,5:1). UI-кит: Pico CSS 2.1.1. Дата: 2026-10-27.

## Colors

- Фон страницы `#FBFDFB` — почти белый с зелёным оттенком · `--pico-background-color`.
- Карточки `#FFFFFF` · `--pico-card-background-color`.
- Текст `#1D2A24` (контраст 14,6:1 к фону) · `--pico-color`, `--pico-h1-color` и остальные заголовки.
- Приглушённый текст `#566860` — подписи и примечания (5,8:1) · `--pico-muted-color`.
- Линии и рамки `#D9E6DE` · `--pico-muted-border-color`.
- Акцент `#007A50` (джейд) — кнопки, ссылки, номера шагов · `--pico-primary`, `--pico-primary-background`, `--pico-primary-underline` (тот же цвет с прозрачностью 0,5); при наведении `#00633F` · `--pico-primary-hover-background`. Основа — цветовая тема Pico `jade`, затемнена ради контраста.
- Текст на акценте `#FFFFFF` (5,4:1) · `--pico-primary-inverse`.
- Подложка примечаний `#E4F3EA` — светлый оттенок акцента, только фон · собственная переменная поверх `--pico-*`.

## Typography

- Заголовки и текст: **Onest**, начертания 400 и 800, кириллица ✅, лицензия SIL OFL 1.1 (бесплатно) · https://fonts.google.com/specimen/Onest · `--pico-font-family`. Файлы шрифта лежат в `site/fonts/`, внешних запросов к Google нет.
- Код: системный моноширинный шрифт Pico (`--pico-font-family-monospace`), отдельный шрифт не подключаем.
- Шкала: заголовки 32 / 52 px (2 / 3,25 rem); базовый размер текста задаёт Pico (16 px на телефоне, 18 px от 768 px), подписи 14,4 px.
- Заголовок h1 на телефоне уменьшается через `clamp()` до 2 rem, чтобы длинные русские заголовки не ломали строку.

## Layout

Одна колонка до 720 px по центру (`.container` Pico), на телефоне 360 px поля по 16 px. Вертикальный ритм: блоки через 4 rem, внутри блока 1–2 rem · `--pico-block-spacing-vertical`. Блоки кода и таблицы прокручиваются внутри себя, страница вбок не прокручивается.

## Elevation & Depth

Теней почти нет: карточки отделяются тонкой рамкой `#D9E6DE`, а не тенью. Без размытых свечений и стеклянных эффектов.

## Shapes

Скругление карточек 1 rem, кнопок и примечаний 0,75 rem, мелких элементов 0,5 rem · `--pico-border-radius` (0,75 rem для страницы) · стандартное 0,25 rem заменено ради «дружелюбности».

## Components

- Кнопка основная: зелёный фон, белый текст 800, скругление 0,75 rem, один призыв на страницу (вверху и внизу — одна и та же кнопка) · `role="button"`.
- Карточка: белая, рамка `#D9E6DE`, скругление 1 rem, внутри заголовок шага и одна-две строки текста · `<article>`.
- Примечание («Codex проверен лишь на базовом уровне», «Пример на демо-данных»): подложка `#E4F3EA`, скругление 0,75 rem.
- Код и таблица: белая подложка, рамка, внутренняя горизонтальная прокрутка · `<pre>`, `<figure>` с таблицей.

## Do's and Don'ts

- Do используй акцент только для кнопок, ссылок и номеров шагов: один яркий цвет на странице.
- Do держи контраст текста не ниже 4,5:1 (проверено для всех пар из раздела Colors).
- Do заголовки пиши крупно, по-русски и без английских терминов там, где есть русское слово.
- Don't применяй градиенты, свечения, тёмную тему, фиолетовые и синие акценты; второй акцентный цвет не вводи.
- Don't подключай больше одного шрифта и больше двух начертаний (400 и 800).
- Don't пиши цвета и размеры в разметке: только переменные `--pico-*` и значения из этого файла.
- Don't смешивай иконки разных наборов: только Lucide.
