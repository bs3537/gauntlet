# Damodaran — Dilution, Future Financing & Share Count in Value/Share

**Source:** Aswath Damodaran, *Investment Valuation: Tools and Techniques for Determining the Value of Any Asset*, 3rd ed. (Wiley). Extracted full text: `damodaran_investment_valuation_fulltext.txt` (993 PDF pages; page-delimited with `===== PAGE N (label=PRINTED) =====` markers). Page references below give the **printed page** number; PDF index in brackets.

Curated for building the Claude Code / Codex **valuation skill** (WSL). These are the passages that govern whether a clinical-stage / money-losing firm's *future* dilutive raises should reduce value per share. The short answer: **no — not for a fair-value raise, because the negative cash flows already capture it; double-charging is "double counting."**

---

## (a) Future dilution is already in the present value — do not re-charge for it

> "This expected dilution in future years will reduce the value of equity per share today. In the FCFE model, the negative free cash flows to equity in the earlier years will reduce the estimated value of equity today. Thus the dilution effect is captured in the present value, and no additional consideration is needed of new stock issues in future years and the effect on value per share today."
> — **printed p.371** [PDF p.390]

*Negative early FCFE = the cash the firm must raise. Discounting it already imposes the dilution cost; a further per-share penalty would charge twice.*

## (b) Divide by the CURRENT (primary) share count, not a projected post-raise count

> "...This value should then be divided by the actual number of shares outstanding to arrive at the equity value per share. Since Tesla will probably have to issue more shares in the next few years to cover its reinvestment needs, you may wonder why we do not incorporate these additional shares when computing value per share."
> — **printed p.658** [PDF p.677]

> "Value of equity per share = (Value of equity − Value of options outstanding) / Primary number of shares outstanding"
> — **printed p.447** [PDF p.466]

*The denominator is current/primary shares. The Tesla example is explicitly a money-losing growth firm with certain future raises.*

## (c) Using a future enlarged share count is "double counting"

> "The reduction in value of $1,306 million ... from bringing in the expected cash flows over the next 10 years, can be considered the dilution discount to current value, and incorporating the additional shares in the denominator would be double counting."
> — **printed p.658–659** [PDF p.677–678]

*The PV of the negative cash flows IS the dilution discount. Enlarging the denominator on top double-counts.*

## (d) THE EXCEPTION — issuing shares BELOW value transfers wealth (this is the only real per-share hit)

> "...The reason there is dilution is because the additional shares are issued only to the option holders at a price below the current price. In contrast, the dilution that occurs in a rights issue where every stockholder gets the right to buy additional shares at a lower price is value neutral. The shares will trade at a lower price but everyone will have more shares outstanding."
> — **printed p.443** [PDF p.462], footnote

*A fair-value raise is value-neutral. Only a below-value issuance to a subset (or a forced distressed raise) genuinely impairs existing holders.*

## (e) Options/warrants — value them as a liability, subtract, then divide by primary shares

> "The correct approach to dealing with options is to estimate the value of the options today ... it is subtracted from the equity value, and then divided by the number of shares outstanding to arrive at value per share."
> — **printed p.446** [PDF p.465]

*Fully-diluted and treasury-stock shortcuts are described as inferior; value options via an option-pricing model as an equity claim.*

---

## Application rule (clinical-stage biotech with rNPV that already nets R&D)

1. rNPV already subtracts PV(remaining R&D / Phase 3). That captures the cash the company must raise.
2. A future raise **at fair value** is per-share neutral — cash in = value of shares out. **Do not** deduct a separate "dilution leak" and **do not** inflate the share count.
3. **Keep** real cash costs not inside the per-asset rNPV (e.g., corporate G&A / pre-launch overhead) — those are genuine outflows, not financing artifacts.
4. Divide intrinsic equity value by the **current** share count (treat options as a valued liability if material).
5. The **only** legitimate per-share financing hit is a raise **below intrinsic value** (distress / forced discount). Put it in the **bear scenario**, weighted by probability — not as a structural haircut to base-case fair value.

**Caveats (Damodaran-consistent):** if distress probability is material, use the distress-adjusted value `DCF×(1−P[distress]) + DistressSale×P[distress]` (printed p.319 [PDF p.338]); model genuinely sub-fair-value raises as reduced proceeds in the cash flows, not as a denominator fudge; handle option overhang via the option-as-liability method (p.446).

---
*Generated 2026-06-24 from the stored full-text extraction. Verbatim quotes; page anchors verifiable against the page-delimited full-text file.*
