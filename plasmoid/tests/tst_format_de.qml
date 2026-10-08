import QtQuick
import QtTest
import "../io.github.flexomatic81.limitrings/contents/code/format.js" as F

TestCase {
    id: testCase
    name: "FormatGerman"

    // Small stand-in for the German catalog: msgid (with context as "ctx|msgid") → msgstr
    readonly property var de: ({
        "billion abbreviation|B": "Mrd",
        "Qt date format for the daily chart tooltip (day and month)|MMM d": "dd.MM.",
        "daily chart tooltip: %1 date, %2 token count|%1: %2 tokens": "%1: %2 Tokens",
        "Since weekly reset (%1)": "Seit Wochen-Reset (%1)",
        "%1 file unreadable – numbers incomplete": ["%1 Datei nicht lesbar – Zahlen unvollständig",
                                                     "%1 Dateien nicht lesbar – Zahlen unvollständig"],
        "limit name: weekly window|Week": "Woche",
        "limit name: weekly window of one model, %1 = model|Week %1": "Woche %1",
        "breakdown entry for all remaining projects or models|Other": "Andere",
        "%1 = clock time; the provider asked to wait before the next request|paused by the provider until %1":
            "vom Anbieter pausiert bis %1",
        "Claude's paid usage beyond the plan limits|Extra usage": "Zusatznutzung",
        "%1 = amount spent, %2 = monthly spending limit|%1 of %2": "%1 von %2",
        "%1 = amount spent; extra usage without a monthly limit|%1 spent": "%1 ausgegeben",
        "Codex credit balance|unlimited": "unbegrenzt",
        "limit structure change: %1 limit name, %2 date|%1: new limit (since %2)": "%1: neues Limit (seit %2)",
        "limit name: 5-hour window|5 h": "5 h"
    })

    function subst(text, args) {
        return text.replace(/%(\d)/g, (m, d) => args[d - 1] !== undefined ? String(args[d - 1]) : m)
    }

    function init() {
        const de = testCase.de, subst = testCase.subst
        F.init({
            i18n: (text, ...a) => subst(de[text] || text, a),
            i18nc: (ctx, text, ...a) => subst(de[ctx + "|" + text] || text, a),
            i18np: (s, p, n, ...a) => {
                const t = de[s]
                return subst(t ? t[n === 1 ? 0 : 1] : (n === 1 ? s : p), [n].concat(a))
            },
            locale: Qt.locale("de_DE")
        })
    }

    function cleanup() { F.init(null) }

    function test_extra_usage_is_german() {
        compare(F.extraName({kind: "extra_usage"}), "Zusatznutzung")
        compare(F.extraText({kind: "extra_usage", used: 12.34, limit: 50, percent: 24.68, currency: "USD"}),
                "12,34\u00a0$ von 50,00\u00a0$")
        compare(F.extraText({kind: "extra_usage", used: 2.5, limit: null, percent: null, currency: "EUR"}),
                "2,50\u00a0€ ausgegeben")
        compare(F.extraText({kind: "credits", balance: 1250.5, unlimited: false}), "1.250,50")
        compare(F.extraText({kind: "credits", balance: 0, unlimited: true}), "unbegrenzt")
    }

    function test_pause_hint_is_german() {
        const t = Date.parse("2026-10-04T18:00:00+02:00")
        const until = new Date(t + 30 * 60000)
        const text = F.footerText({limits_updated_at: "2026-10-04T17:55:00+02:00", limits_source: "oauth",
                                   limits: [], limits_paused_until: until.toISOString()}, t)
        verify(/ · vom Anbieter pausiert bis \d\d:\d\d$/.test(text), text)
    }

    function test_numbers() {
        compare(F.formatInt(1234567), "1.234.567")
        compare(F.compactNumber(1234567), "1,2 M")
        compare(F.compactNumber(2500000000), "2,5 Mrd")
    }

    function test_day_tooltip() {
        compare(F.dayTooltip({date: "2026-10-04", total: 1234}), "04.10.: 1.234 Tokens")
    }

    function test_weekday_has_no_trailing_dot() {
        // 12:00 UTC: a Saturday in every common timezone
        const title = F.breakdownTitle({basis: "window", since: "2026-10-03T12:00:00Z"})
        verify(/^Seit Wochen-Reset \(Sa \d\d:\d\d\)$/.test(title), title)
    }

    function test_limit_names_and_errors() {
        compare(F.limitName({id: "seven_day", window_minutes: 10080}), "Woche")
        compare(F.limitName({id: "s", window_minutes: 10080, model: "Opus"}), "Woche Opus")
        compare(F.errorText([{code: "logs_unreadable", count: 2}]), "2 Dateien nicht lesbar – Zahlen unvollständig")
        compare(F.breakdownRows([{name: null, other: true, total: 1}], 1)[0].name, "Andere")
    }

    function test_changesText_in_german() {
        compare(F.changesText([{kind: "new", limit: {id: "seven_day_opus", window_minutes: 10080, model: "Opus"},
                                at: "2026-10-02T12:00:00+02:00"}]), "Woche Opus: neues Limit (seit 02.10.)")
    }
}
