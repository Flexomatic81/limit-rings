// Translator for core.mjs in the Übersicht widget: German texts from de.json when the system language is German,
// English otherwise; numbers and weekdays always in the system's format.

function _subst(text, args) {
    return text.replace(/%(\d)/g, (m, d) => args[d - 1] !== undefined ? String(args[d - 1]) : m)
}

export function isGerman(language) {
    return typeof language === "string" && /^de\b/i.test(language)
}

export function makeTranslator(language, catalog) {
    const cat = isGerman(language) && catalog ? catalog : {}
    const lang = typeof language === "string" && language ? language : "en-US"
    const one = new Intl.NumberFormat(lang, {minimumFractionDigits: 1, maximumFractionDigits: 1})
    const whole = new Intl.NumberFormat(lang, {maximumFractionDigits: 0})
    const day = new Intl.DateTimeFormat(lang, {weekday: "short"})
    const lookup = key => (typeof cat[key] === "string" && cat[key]) || null
    return {
        i18n: (text, ...args) => _subst(lookup(text) || text, args),
        i18nc: (context, text, ...args) => _subst(lookup(context + "\u0004" + text) || text, args),
        i18np: (singular, plural, n, ...args) => {
            const forms = Array.isArray(cat[singular]) ? cat[singular] : [singular, plural]
            return _subst(n === 1 ? forms[0] : forms[forms.length - 1], [n].concat(args))
        },
        decimal: x => one.format(x),
        integer: n => whole.format(Math.round(n)),
        // 2024-01-07 was a Sunday: day d of the week is that date plus d days
        weekday: d => day.format(new Date(2024, 0, 7 + d)).replace(/\.$/, "")
    }
}
