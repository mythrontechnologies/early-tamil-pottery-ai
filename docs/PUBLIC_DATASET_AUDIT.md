# Public Dataset Audit (Milestone 6)

**Date:** 2026-09-23
**Question:** Is there openly licensed image data for Early Historic Tamil Nadu pottery,
especially Tamil-Brahmi / Tamiḻi inscribed or graffiti-bearing sherds?

**Answer:**

> **No directly suitable openly licensed Tamil Nadu Early Historic pottery dataset was
> found.** No repository publishes a labelled, provenanced, openly licensed collection of
> inscribed Tamil Nadu sherds.

What does exist are individual photographs by Wikimedia contributors, uploaded as their
own work under CC BY or CC BY-SA. They show pottery on display at the Keezhadi site
museum and burial urns in situ at Adichanallur and Sivakalai. These photographs carry no
expert labels, catalogue numbers or find contexts. They were acquired as **unlabelled
candidate images**, alongside separately stored supporting material.

A licence was accepted only when it was read from the original source's own API. Search
engines, blogs, mirrors and "free to view" pages were never treated as a licence.

---

## 1. Sources searched

Searches were run through official APIs wherever one exists. Exact search terms are
listed per source. **Relevant?** is about subject matter only; **Usable?** is about rights.

### 1.1 Wikimedia Commons (MediaWiki API: `list=search`, `categorymembers`, `imageinfo`)

Terms: `Tamil Brahmi pottery`, `Tamil-Brahmi potsherd`, `Tamil Brahmi potsherd`,
`Tamil Brahmi inscription`, `Keeladi pottery`, `Keezhadi pottery`, `Keeladi potsherd`,
`Keezhadi potsherd`, `Kodumanal`, `Porunthal`, `Alagankulam`, `Arikamedu pottery`,
`Adichanallur urn`, `Adichanallur pottery`, `Sivagalai`, `Korkai excavation`,
`Keeladi museum`, `Keezhadi museum`, `Pattanam excavation museum`, `Puducherry Museum`,
`Government Museum Chennai pottery`, `rouletted ware`, `black and red ware`,
`graffiti marks pottery`, `potsherd India`, `megalithic pottery Tamil Nadu`,
`Porunai museum`, `Adichanallur archaeological site`.

Categories inspected (every file's licence, author, credit and description read from
`extmetadata`): Keezhadi archeological site (174 files), Keezhadi Museum, Adichanallur
earthenware burial urns, Adichanallur archaeological site, Sivakalai archaeological site,
Arikamedu (86), Pattanam, Pattanam excavation museum, Black and Red Ware, Tamil Brahmi
inscriptions and its sub-categories.

Findings:

- **Kodumanal, Porunthal, Alagankulam:** no pottery images at all. One Kodumanal file is a
  TNSDA banner re-uploaded under "GODL-India".
- **Keezhadi:** mostly trench, site and museum-building photographs. One uploader
  (Rajeshodayanchal, 134 photos, CC BY-SA 4.0) photographed the site museum, including
  close-ups of individual incised sherds. Captions are generic.
- **Adichanallur / Sivakalai:** in-situ burial urns, CC BY / CC BY-SA 4.0, own work.
- **Tamil-Brahmi on pottery:** only outside Tamil Nadu (Pattanam and Muziris in Kerala;
  Tissamaharama in Sri Lanka).
- **Tamil-Brahmi rock and cave inscriptions:** several own-work photographs (Jambai,
  Nehanurpatti, Arittapatti, Kongar Puliyankulam), plus photographs of replicas
  (Mangulam models).

### 1.2 Other repositories

| Source | Method | Terms | Result |
|---|---|---|---|
| Zenodo | REST API `/api/records` | Tamil Brahmi; Tamil-Brahmi; Brahmi inscription; Brahmi script dataset; Keeladi; Keezhadi; potsherd India; graffiti marks megalithic pottery; South India pottery; pottery sherd images deep learning | No Tamil Nadu pottery images. Candidates examined: §2. |
| Hugging Face Datasets | `/api/datasets?search=` | brahmi; tamil brahmi; pottery; potsherd; archaeology ceramics; tamil inscription | No Brahmi or Tamil-Brahmi datasets. Eight "pottery" datasets: Greek pottery, the Beazley archive, or no licence. None relevant. |
| GitHub | REST search API | tamil brahmi dataset; brahmi dataset; brahmi ocr; tamil-brahmi; ancient tamil script dataset; pottery sherd dataset; keeladi | Student OCR projects. Almost all have **no licence**. One is CC0 (§2). |
| Figshare | `/v2/articles/search` | Tamil Brahmi; Brahmi inscription; potsherd India; Tamil Nadu pottery | One relevant item: a table, not images (§2). |
| Openverse | `/v1/images/` | Tamil Brahmi; Keeladi; potsherd Tamil Nadu; Adichanallur; Brahmi inscription | Everything relevant is re-indexed Wikimedia Commons. Flickr results are CC BY-NC or BY-NC-ND. |
| Kaggle | dataset API (`/api/v1/datasets/view`) | Brahmi dataset | `gautamneha/brahmi-dataset`: licence **"Data files © Original Authors"**. |
| The Met Open Access (CC0) | collection API | Tamil Nadu; Arikamedu; Andhra Pradesh sherd; South India earthenware | Tamil Nadu holdings are bronzes and sculpture. **No South Indian pottery or sherds.** |
| Cleveland Museum of Art Open Access (CC0) | open-access API | Tamil Nadu pottery; South India earthenware; Arikamedu | 0 results. |
| Europeana | search API | Tamil Nadu pottery; Arikamedu; potsherd India | 3 results, all non-pottery or restricted (InC-EDU; CC BY-NC-SA). |
| Mendeley Data, Indian open-data portals | web search | Tamil Brahmi pottery dataset; Keeladi open data | Nothing found. The TNSDA site remained unreachable, as in Milestone 4. |

---

## 2. Candidate decisions

### 2.1 Accepted and acquired

The **acquired** column of each row reports the outcome of the run, as confirmed in
`MILESTONE_6_REPORT.md`.

| Source | Licence (read from source API) | Target | Why accepted |
|---|---|---|---|
| Commons: 18 Keezhadi site-museum photos by Rajeshodayanchal | CC BY-SA 4.0 | `data/raw` | Own work; pottery and incised sherds on display in Tamil Nadu. **Find-site not stated by the source**, so geographic scope is recorded as `unknown`. |
| Commons: "Red-Slipped-Pots-Keezhadi…" by N. Vivekananthamoorthy | CC BY 4.0 | `data/raw` | Own work; the source states the pots were excavated at Keezhadi. |
| Commons: 10 "Adichanallur earthenware burial urns" (Perumalism, Venkadesh, Balurbala) | CC BY 4.0 / CC BY-SA 4.0 | `data/raw` | Own work; Tamil Nadu site stated by the source; pottery in situ. |
| Commons: "Urn in Sivakalai Archeology site" by Balurbala | CC BY-SA 4.0 | `data/raw` | Own work; Tamil Nadu site stated by the source. |
| Commons: Pattanam "Tamil-Brahmi Inscription"; "Tamil Brahmi writings found Muziris excavation sites" | CC BY-SA 4.0 | `data/external/supporting_pottery` | Tamil-Brahmi on pottery **per the source title**, but in **Kerala**, so outside the primary scope. |
| Commons: "Tamil Brahmi potsherd Tissamaharama" | CC BY-SA 4.0 | `data/external/supporting_pottery` | Sri Lanka; out of scope; comparison only. |
| Commons: "Black and Red ware" (Kanatonian) | CC BY-SA 3.0 | `data/external/supporting_pottery` | "South Indian type" black-and-red ware **found in Sri Lanka** (per source). |
| Commons: 2 "Painted Potsherds – Govt Museum Egmore" | CC BY 4.0 | `data/external/supporting_pottery` | Held in Chennai, **find-site not stated**; cannot be called Tamil Nadu pottery. |
| Commons: 2 Arikamedu objects at Musée Guimet (PHGCOM, "self-made") | CC BY-SA 4.0 | `data/external/supporting_pottery` | Puducherry, not Tamil Nadu; one is Roman pottery. |
| Commons: 7 Tamil-Brahmi rock and cave inscription photos | CC BY-SA 3.0 / 4.0 | `data/external/tamil_brahmi_inscriptions` | Real Tamil-Brahmi, but **not pottery**. Kept for future OCR work only. |
| Commons (Milestone 11): 4 "Civiltà thamirabani, reperti da adhichanallur" — cup, storage jar, lidded urn, footed vessel — by Sailko | CC BY 3.0 | `data/raw` (`wmc_tamil_nadu_pottery_m11`) | Own work; each photograph shows **one** vessel in the Anthropology Museum, Government Museum, Chennai; Adichanallur per the source title and category. One face visible; the caption date is not an object date. |

### 2.2 Rejected, or leads only

| Source | Licence | Reason |
|---|---|---|
| Commons: "Archaeological Excavation, Kodumanal" | "GODL-India" (asserted by uploader) | Credited to TNSDA. The government licence was asserted by a re-uploader and not verified at the originating portal (A3, A4). A site banner anyway. |
| Commons: "கோவை கௌசிகா நதியில்… தமிழ் பிராமி" | CC BY-SA 4.0 (claimed) | 800×711 image with a press-style scale bar; the own-work claim is doubtful. Needs human review. |
| Commons: "Arittapatti inscriptions in Tamil Brahmi mentioning Paravar" | CC BY-SA 4.0 (claimed) | Description reproduces a news article ("MADURAI SEPT.14 …"); likely not the uploader's own work. |
| Commons: "Mangulam inscription", "Mangulam Tamil Inscriptions 01" | CC BY-SA 3.0 / 4.0 | Photographs of **models (replicas)**, per the source. Not the inscription. |
| Commons: Pattanam "(cropped)" | CC BY-SA 4.0 | A crop of an acquired photograph; a near-duplicate adds nothing. |
| Commons: "Adichanallur archaeological site 01–27" (Perumalism) | CC BY-SA 4.0 | Eligible, but the same pits by the same photographer as acquired files: near-duplicates. Recorded as a lead. |
| Commons: Keezhadi museum panels, hero stones, ring well, building photos | CC BY-SA 4.0 | Not pottery. Panels also reproduce the museum's own designed graphics. |
| Kaggle: `gautamneha/brahmi-dataset` | "Data files © Original Authors" | Not an open licence. |
| GitHub: Tamil/Brahmi OCR repositories | none | No licence means no permission. |
| GitHub: `JackSparrowPK766/Tamil-BrahmiOCR2` | CC0 (repository) | No README and no provenance for the images. A CC0 file cannot license images the author may not own. |
| Zenodo 14961074 "BrahmiGAN" | CC BY 4.0 | **GAN-generated synthetic** Brahmi letters; the brief excludes synthetic data. Recorded as a lead for later OCR experiments, clearly labelled synthetic. |
| Zenodo 3569199 Pauni Brahmi inscription (innag0001.png) | CC BY 4.0 (deposit) | Creator "Anon."; appears to reproduce a figure from the 1972 excavation report, whose rights the depositor may not hold. |
| Zenodo 3544411 Pauni pillar photograph | CC BY 4.0 (deposit) | Brahmi, not Tamil-Brahmi; Maharashtra; creator anonymous. Lead only. |
| Zenodo: British Museum intaglios with Brahmi (e.g. 3804191) | CC BY 4.0 (deposit) | The deposit's CC BY conflicts with the British Museum's own image terms. |
| Zenodo 1149684 / 1149686 Maharashtra surface-pottery collections | CC BY 4.0 | Spreadsheets only, no images. |
| Zenodo 7965768 Early Medieval Pottery Marks, Moravia | CC BY 4.0 | 219 MB of drawings, Czech. A possible future analogue for mark-shape work; not needed now. |
| Figshare 12476789 (Alagankulam / Keeladi pottery chemistry) | CC BY + CC0 | A table of chemical compositions, no images. A knowledge-base lead. |
| Flickr via Openverse (Tamil-Brahmi beds) | CC BY-NC 2.0 | Non-commercial; needs a human decision (A3). |
| Europeana | InC-EDU; CC BY-NC-SA | Not pottery, or restricted. |
| TNSDA 2026 corpus, excavation reports, Internet Archive and Scribd copies | none / © | Milestone 4 findings unchanged: permission required; mirrors are unauthorised. Blocked in code. |

---

## 3. What the acquired data is, and is not

- **Is:** real photographs of real archaeological pottery in Tamil Nadu (Keezhadi site
  museum; Adichanallur and Sivakalai in situ), each under a CC licence read from the source,
  with full provenance and verified checksums.
- **Is not:** labelled data. No source states a script, a reading, a date, a catalogue
  number or an excavation context for any object shown. The Keezhadi museum close-ups
  show incised marks, but **whether those marks are Tamil-Brahmi, graffiti or something
  else is not established**. Every research record therefore has `script_type = unknown`.
- **Is not:** proof of find-site for the museum photographs. A site museum can display
  material from other sites, or replicas; the find-site field says so.
- **Is not:** redistributable without conditions. CC BY and BY-SA require attribution, and
  BY-SA requires share-alike on adaptations. The exact attribution line for every file is
  in `data/metadata/acquisition/provenance.jsonl`.

## 4. Residual rights risks

1. **Uploader warranty.** The licence is the uploader's grant. Commons "own work" plus the
   absence of deletion or copyright-violation flags is the strongest check available without
   contacting each photographer, but it is not a guarantee.
2. **Museum photography terms.** Visitor photography rules at the Keezhadi museum are a
   matter between the visitor and the museum. They do not change the copyright licence of
   the photograph, and the photographed objects (ancient pottery) carry no copyright. Recorded
   for transparency.
3. **Share-alike.** Any adapted image derived from a CC BY-SA file (e.g. a published crop)
   must be released under CC BY-SA. Model weights are not generally considered adaptations
   of individual images, but this is unsettled. Record it before publishing.

## 5. Milestone 11 screening (2026-10-08)

Every file of these Commons categories was listed with its licence, author and description from the API,
and every thumbnail was looked at once, for **eligibility only** (an individual pottery object from Tamil
Nadu that the project may use), never for a class: Keezhadi archeological site (183 files), Keezhadi
Museum, Keezhadi, Keeladi Museum, Sivakalai archaeological site (18), Korkai, Adichanallur archaeological
site (47), Adichanallur earthenware burial urns, Anthropology Museum (Government Museum, Chennai), Arikamedu
(86); plus 31 full-text searches (potsherd, graffiti, Tamil-Brahmi, rouletted ware, Kodumanal, Porunthal,
Alagankulam, Vembakottai, Kilnamandi, Mayiladumparai, Korkai, Uraiyur, Kaveripattinam, …).

| Outcome | Files |
|---|---|
| Acquired | 4 Adichanallur vessels (Sailko, CC BY 3.0), see §2.1 |
| Already held | the 18 Keezhadi files of Milestone 6, including all six individually photographed marked sherds (the pilot) |
| Not pottery | trenches and structures, site and museum buildings, coins, beads, bangles, iron tools, terracotta figurines and balls, hero stones, ring wells, a ship model |
| Not individual objects | showcases and gallery overviews (several vessels; no object identifiable) |
| Reproductions of designed graphics | museum panels and posters (their photographs belong to the museum) |
| In-situ pits | Adichanallur 01–27, Sivakalai trenches: several overlapping urns per photograph, the same vessels from several angles (grouping / leakage risk), one buried face (no `none` judgement possible); decision of Milestone 6 kept |
| Out of scope | Ambari (Guwahati, Assam) rouletted sherds; Arikamedu (Puducherry); Tissamaharama (Sri Lanka); crops of printed catalogue pages ("Catalogue of the prehistoric antiquities from Adichanallur and Perumbair", page crops): reproductions of a publication, not photographs of objects; not examined further |

Conclusion: open sources no longer yield individually photographed **marked** sherds from Tamil Nadu, and
yield nothing for the `none` class. Target 1 needs one institutional permission (`NEXT_DATA_ACQUISITION.md`).
