import test from "node:test"
import assert from "node:assert/strict"
import { makeTranslator, isGerman } from "../limit-rings.widget/lib/i18n.mjs"

const CAT = {"limit name: weekly window\u0004Week": "Woche", "Reset in %1": "Reset in %1",
             "%1 file unreadable – numbers incomplete": ["%1 Datei nicht lesbar", "%1 Dateien nicht lesbar"]}

test("German texts with context and plural", () => {
  const tr = makeTranslator("de-DE", CAT)
  assert.equal(tr.i18nc("limit name: weekly window", "Week"), "Woche")
  assert.equal(tr.i18np("%1 file unreadable – numbers incomplete", "%1 files unreadable – numbers incomplete", 3),
               "3 Dateien nicht lesbar")
  assert.equal(tr.i18n("Not in the catalog %1", "x"), "Not in the catalog x")
  assert.equal(tr.decimal(1.25), "1,3")
  assert.equal(tr.integer(12345), "12.345")
  assert.equal(tr.weekday(1), "Mo")
})

test("unknown language falls back to English", () => {
  const tr = makeTranslator("fr-FR", CAT)
  assert.equal(tr.i18nc("limit name: weekly window", "Week"), "Week")
  assert.equal(tr.decimal(1.25), "1,3")      // the system's number format stays
  assert.equal(isGerman("de"), true)
  assert.equal(isGerman("fr-FR"), false)
  assert.equal(isGerman(undefined), false)
})
