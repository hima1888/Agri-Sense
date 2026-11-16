"""Structured disease knowledge for every disease class the installed models can output.

Content is general plant-pathology guidance compiled from standard references (APS disease compendia, the CABI
Crop Protection Compendium, university and ICAR extension guides). It names no products or doses: chemical
control must follow the locally registered label and local advice. It has NOT been reviewed by a local
agronomist; the API and UI say so. A test checks that every model label maps to an entry.
"""

# ruff: noqa: E501, RUF001  (prose; en dashes in ranges are intended)
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

SOURCE = (
    "General guidance compiled from standard plant-pathology references (APS disease compendia, CABI Crop "
    "Protection Compendium, university and ICAR extension guides). Not reviewed by a local agronomist; "
    "practices and registered products differ by region."
)
SEEK_ADVICE_COMMON = (
    "Before any chemical treatment, before removing large numbers of plants, if the problem spreads quickly "
    "despite action, or if you are unsure of the diagnosis: contact your local agricultural extension officer "
    "(in India: Krishi Vigyan Kendra or the state agricultural university)."
)


@dataclass(frozen=True)
class DiseaseInfo:
    key: str
    name: str
    pathogen: str
    pathogen_type: str  # fungus | oomycete | bacterium | virus | mite
    crops: tuple[str, ...]
    what: str
    symptoms: tuple[str, ...]
    causes: str
    conditions: str
    spread: str
    management: tuple[str, ...]
    prevention: tuple[str, ...]
    sustainable: tuple[str, ...]
    monitor: tuple[str, ...]
    seek_advice: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["seek_advice"] = f"{self.seek_advice} {SEEK_ADVICE_COMMON}".strip()
        d["source"] = SOURCE
        d["reviewed"] = False
        return d


_FUNGICIDE = "If pressure is high: a fungicide registered locally for this disease, applied exactly per the label and rotated between modes of action to slow resistance."
_RESIDUE = "Remove and destroy (do not compost) infected crop residue after harvest."
_ROTATE = "Rotate away from host crops for at least 2 years."

E = DiseaseInfo
ENTRIES: tuple[DiseaseInfo, ...] = (
    E(
        "apple_scab",
        "Apple scab",
        "Venturia inaequalis",
        "fungus",
        ("apple",),
        "A fungal disease of apple leaves and fruit, the most important apple disease in humid regions.",
        (
            "Olive-green to brown velvety spots on leaves, later dark and scabby",
            "Dark, corky, cracked spots on fruit",
            "Early leaf drop in severe cases",
        ),
        "The fungus overwinters in fallen infected leaves and releases spores in spring rain.",
        "Cool (about 10–24 °C), wet springs; leaves wet for many hours after rain.",
        "Spores from old leaves are splashed and blown onto new leaves; leaf spots then produce more spores through the season.",
        (
            "Remove or shred fallen leaves in autumn to cut the overwintering source",
            "Prune for open canopies that dry quickly",
            _FUNGICIDE,
        ),
        ("Plant scab-resistant varieties", "Avoid overhead irrigation"),
        (
            "Leaf-litter removal to cut the spore source",
            "Spray only in infection periods (wet and mild), not on a calendar",
        ),
        ("Leaf-wetness hours and temperature after spring rain", "New spots on young leaves each week"),
        "If more than a few percent of leaves or fruit are spotted early in the season.",
    ),
    E(
        "apple_black_rot",
        "Apple black rot",
        "Botryosphaeria obtusa",
        "fungus",
        ("apple",),
        "A fungal disease causing leaf spots, fruit rot and branch cankers on apple.",
        (
            "'Frog-eye' leaf spots: purple margin, tan centre",
            "Firm brown-black fruit rot with rings, often from the blossom end",
            "Sunken cankers on branches",
        ),
        "The fungus survives in dead wood, cankers and mummified fruit left in the tree.",
        "Warm (about 20–30 °C), wet weather; trees stressed by drought, frost or wounds.",
        "Rain splash carries spores from cankers and mummies to leaves, fruit and wounds.",
        (
            "Prune out dead wood and cankers in dry weather",
            "Remove mummified fruit from trees and the ground",
            _FUNGICIDE,
        ),
        ("Avoid wounding; control insects that damage fruit", "Keep trees vigorous (water, nutrition)"),
        ("Sanitation pruning removes most of the inoculum without sprays",),
        ("Cankers during winter pruning", "Leaf spots after warm rain"),
        "If branch cankers are widespread or fruit rot exceeds a few percent.",
    ),
    E(
        "cedar_apple_rust",
        "Cedar apple rust",
        "Gymnosporangium juniperi-virginianae",
        "fungus",
        ("apple",),
        "A rust fungus that needs two hosts: apple and eastern red cedar / juniper.",
        (
            "Bright yellow-orange leaf spots, later with tiny tubes underneath",
            "Orange jelly-like horns on galls on nearby junipers in spring",
        ),
        "Spores from galls on juniper infect apple in spring; it cannot spread from apple to apple.",
        "Warm, wet spring weather while apple leaves are young.",
        "Wind carries spores from junipers (up to a few km) to apple leaves.",
        ("Remove nearby junipers or their galls where practical", _FUNGICIDE),
        ("Plant rust-resistant apple varieties", "Avoid planting apples next to junipers"),
        ("Removing the alternate host breaks the cycle without sprays",),
        ("Galls on junipers in late winter", "Yellow spots after spring rain"),
        "If defoliation is significant two seasons in a row.",
    ),
    E(
        "cherry_powdery_mildew",
        "Cherry powdery mildew",
        "Podosphaera clandestina",
        "fungus",
        ("cherry",),
        "A fungal disease forming white powdery growth on cherry leaves and fruit.",
        (
            "White powdery patches on leaves, often with curling",
            "Faint white bloom on fruit, later russeting",
        ),
        "The fungus overwinters on buds and bark and grows on the surface of young tissue.",
        "Warm days, high humidity and mild nights; unlike most fungi it does not need rain.",
        "Wind-borne spores from infected shoots to new growth.",
        ("Prune infected shoots", "Open the canopy for air movement", _FUNGICIDE),
        ("Avoid excess nitrogen (soft growth is most susceptible)", "Choose less susceptible varieties"),
        ("Sulphur-based or biological products where locally approved",),
        ("New shoots and leaf undersides in humid weeks",),
        "If fruit infection appears before harvest.",
    ),
    E(
        "gray_leaf_spot",
        "Gray leaf spot of maize",
        "Cercospora zeae-maydis",
        "fungus",
        ("corn",),
        "A fungal leaf disease of maize that reduces yield when leaves die early.",
        (
            "Narrow, rectangular grey-tan lesions bounded by leaf veins",
            "Lesions merge and blight leaves from the bottom up",
        ),
        "The fungus survives on maize residue left on the soil surface.",
        "Warm (about 25–30 °C), very humid weather with long dew periods; reduced tillage; continuous maize.",
        "Spores from residue are blown and splashed onto lower leaves, then move up the plant.",
        ("Rotate with a non-host crop", "Bury or remove residue where erosion allows", _FUNGICIDE),
        ("Plant tolerant hybrids", "Avoid continuous maize in the same field"),
        ("Rotation with legumes cuts inoculum and adds nitrogen",),
        ("Lower leaves from knee height to tasselling",),
        "If lesions reach the ear leaf before grain filling.",
    ),
    E(
        "corn_common_rust",
        "Common rust of maize",
        "Puccinia sorghi",
        "fungus",
        ("corn",),
        "A rust fungus producing rusty pustules on maize leaves.",
        (
            "Small, raised, cinnamon-brown powdery pustules on both leaf surfaces",
            "Pustules turn black late in the season",
        ),
        "Spores blow in from warmer regions or from the alternate host (Oxalis); they do not survive on residue.",
        "Cool to moderate temperatures (about 16–23 °C) with high humidity or dew.",
        "Wind carries spores long distances; each pustule produces new spores every 1–2 weeks.",
        ("Usually no action on tolerant hybrids", _FUNGICIDE),
        ("Plant resistant hybrids", "Sow at the recommended time"),
        ("Resistant hybrids are the main and most sustainable control",),
        ("Pustules on the upper leaves before tasselling",),
        "If many pustules appear on the upper leaves before tasselling.",
    ),
    E(
        "northern_leaf_blight",
        "Northern leaf blight of maize",
        "Exserohilum turcicum",
        "fungus",
        ("corn",),
        "A fungal leaf blight of maize producing long grey-green lesions.",
        ("Long (2.5–15 cm) cigar-shaped grey-green to tan lesions", "Lesions start on lower leaves"),
        "The fungus survives on infected maize residue.",
        "Moderate temperatures (about 18–27 °C) with heavy dew or frequent rain.",
        "Wind and rain carry spores from residue to leaves.",
        (_ROTATE, _RESIDUE, _FUNGICIDE),
        ("Plant resistant hybrids", "Avoid continuous maize"),
        ("Rotation and residue management",),
        ("Leaves around the ear before grain fill",),
        "If lesions reach the ear leaf before grain fill.",
    ),
    E(
        "grape_black_rot",
        "Grape black rot",
        "Guignardia bidwellii (Phyllosticta ampelicida)",
        "fungus",
        ("grape",),
        "A fungal disease of grapevine leaves, shoots and berries.",
        (
            "Reddish-brown round leaf spots with a dark border and tiny black dots",
            "Berries turn brown, then shrivel into hard black 'mummies'",
        ),
        "The fungus overwinters in mummified berries and cane lesions.",
        "Warm (about 20–30 °C), wet weather from bloom until the berries begin to ripen.",
        "Rain splashes spores from mummies to young leaves and berries.",
        (
            "Remove all mummies from the vine and the ground before bud break",
            "Prune for an open canopy",
            _FUNGICIDE,
        ),
        ("Good canopy management and sanitation",),
        ("Sanitation sharply reduces the need for sprays",),
        ("Leaf spots after rain", "Berries from bloom to the start of ripening"),
        "If berries are affected around bloom.",
    ),
    E(
        "grape_esca",
        "Esca (black measles)",
        "Fungal trunk-disease complex (Phaeomoniella chlamydospora, Phaeoacremonium spp. and others)",
        "fungus",
        ("grape",),
        "A wood disease of grapevine trunks; leaf symptoms are a sign of internal wood decay.",
        (
            "'Tiger-stripe' leaves: yellow or red bands between veins that dry out",
            "Dark spots on berries",
            "Sudden wilting of a whole vine in hot weather",
        ),
        "Fungi enter through pruning wounds and colonise the wood over years.",
        "Spores are released in rain; hot summers after wet periods bring out leaf symptoms.",
        "Spores infect fresh pruning wounds; it does not spread through leaves.",
        (
            "Mark and prune out symptomatic wood; replace dead vines",
            "There is no cure once the trunk is colonised",
        ),
        ("Prune in dry weather and protect large pruning wounds", "Use clean planting material"),
        ("Wound protection and timing of pruning (there are no curative chemicals)",),
        ("Leaf symptoms in mid-summer; mark affected vines",),
        "For lab confirmation, and before replanting a block.",
    ),
    E(
        "grape_isariopsis_leaf_spot",
        "Isariopsis leaf spot (grape leaf blight)",
        "Pseudocercospora vitis",
        "fungus",
        ("grape",),
        "A fungal leaf spot of grapevine, mostly in warm, humid regions.",
        ("Irregular dark brown spots on older leaves, later with a dark border", "Early leaf drop"),
        "The fungus survives on infected leaves.",
        "Warm, humid weather late in the season.",
        "Wind and rain splash carry spores.",
        ("Remove fallen leaves", "Improve canopy airflow", _FUNGICIDE),
        ("Balanced nutrition and canopy management",),
        ("Sanitation; spray only around wet periods",),
        ("Older leaves late in the season",),
        "If leaves drop before harvest.",
    ),
    E(
        "citrus_greening",
        "Citrus greening (Huanglongbing, HLB)",
        "Candidatus Liberibacter asiaticus",
        "bacterium",
        ("orange",),
        "A bacterial disease of citrus spread by the Asian citrus psyllid; there is no cure and infected trees decline.",
        (
            "Blotchy, uneven yellow mottling on leaves",
            "Small, lopsided, bitter fruit that stays green at the bottom",
            "Twig dieback",
        ),
        "Bacteria live in the tree's food-conducting tissue (phloem) and block it.",
        "Wherever the psyllid vector is present; warm climates.",
        "The Asian citrus psyllid (Diaphorina citri) carries the bacteria from tree to tree; also infected budwood.",
        (
            "Report suspected trees; removal is usually advised to protect the orchard",
            "Control psyllids in an area-wide programme",
        ),
        ("Plant certified disease-free nursery trees", "Monitor and manage psyllids"),
        ("Coordinated area-wide psyllid management; biological control (Tamarixia radiata) where available",),
        ("Psyllids on new flush", "Blotchy mottle on leaves"),
        "Immediately: a lab test (PCR) is needed to confirm, and it is a regulated disease in many regions.",
    ),
    E(
        "peach_bacterial_spot",
        "Bacterial spot of peach",
        "Xanthomonas arboricola pv. pruni",
        "bacterium",
        ("peach",),
        "A bacterial disease of stone fruit causing leaf spots, 'shot holes' and fruit spots.",
        (
            "Small angular purple-brown leaf spots that fall out, leaving holes",
            "Pitted, cracked spots on fruit",
            "Yellowing and leaf drop",
        ),
        "Bacteria overwinter in twig cankers and buds.",
        "Warm, wet, windy weather; sandy soils.",
        "Wind-driven rain splashes bacteria from cankers to leaves and fruit.",
        (
            "Copper-based or other locally registered bactericides per label (fungicides do not control bacteria)",
            "Prune out cankered twigs",
        ),
        ("Plant resistant varieties", "Windbreaks"),
        ("Resistant varieties and windbreaks reduce reliance on copper",),
        ("Leaf spots after storms", "Fruit spots early in the season"),
        "If fruit spotting appears early in the season.",
    ),
    E(
        "bacterial_spot",
        "Bacterial spot of tomato and pepper",
        "Xanthomonas spp. (X. euvesicatoria, X. vesicatoria, X. perforans, X. gardneri)",
        "bacterium",
        ("tomato", "bell pepper"),
        "A bacterial disease of tomato and pepper leaves, stems and fruit.",
        (
            "Small, dark, water-soaked leaf spots, sometimes with a yellow halo",
            "Raised scabby spots on fruit",
            "Leaf drop that exposes fruit to sunscald",
        ),
        "Bacteria arrive on infected seed or transplants and survive on crop debris and volunteer plants.",
        "Warm (about 24–30 °C), wet weather; overhead irrigation; storms.",
        "Rain splash, overhead water, and hands and tools moving through wet plants.",
        (
            "Remove badly affected plants early",
            "Copper-based products registered locally, per label (resistance is common)",
            "Avoid working among wet plants",
        ),
        ("Use certified clean seed and transplants", "Drip instead of overhead irrigation", _ROTATE),
        ("Hot-water seed treatment, drip irrigation and rotation",),
        ("New leaf spots after rain", "Fruit spots"),
        "If symptoms appear on transplants or spread quickly after rain.",
    ),
    E(
        "early_blight",
        "Early blight",
        "Alternaria solani (on tomato also A. linariae)",
        "fungus",
        ("potato", "tomato"),
        "A common fungal disease of potato and tomato that starts on older leaves.",
        (
            "Brown leaf spots with concentric rings (a 'target' pattern), often with a yellow halo",
            "Starts on lower, older leaves",
            "Dark sunken lesions on stems, or on tomato fruit near the stem",
        ),
        "The fungus survives on infected crop residue and in soil; stressed or older plants are most susceptible.",
        "Warm (about 24–29 °C) weather alternating between wet and dry; heavy dew.",
        "Wind, rain splash and tools carry spores from residue and lower leaves.",
        ("Remove infected lower leaves", "Mulch to stop soil splashing onto leaves", _FUNGICIDE),
        (_ROTATE, "Balanced fertilisation (nitrogen and potassium)", "Wide spacing for airflow"),
        ("Mulching, rotation and resistant varieties reduce fungicide use",),
        ("Lower leaves weekly, especially after fruit set or tuber initiation",),
        "If lesions move into the upper canopy before harvest.",
    ),
    E(
        "late_blight",
        "Late blight",
        "Phytophthora infestans",
        "oomycete",
        ("potato", "tomato"),
        "A fast, destructive water-mould disease of potato and tomato that can kill a field within days.",
        (
            "Large, dark, water-soaked leaf lesions with pale green edges",
            "White fluffy growth on the leaf underside in humid weather",
            "Dark brown stem lesions; firm brown rot of tomato fruit and potato tubers",
        ),
        "The pathogen survives in infected tubers (seed, cull piles, volunteers) and spreads from there.",
        "Cool (about 10–20 °C), very humid or rainy weather; long leaf wetness.",
        "Wind carries spores long distances and rain splashes them; tubers are infected from the soil.",
        (
            "Act immediately: destroy infected plants (bag them, do not compost)",
            "Protective products registered locally against late blight, per label; applying them before infection matters most",
            "Kill potato haulms before harvest if the foliage is infected",
        ),
        (
            "Plant certified disease-free seed tubers",
            "Destroy cull piles and volunteer plants",
            "Hill potatoes well to protect tubers",
            "Resistant varieties",
        ),
        ("Forecast-based spraying (only in blight-favourable weather)", "Resistant varieties"),
        (
            "Blight-favourable weather (cool and humid for 2 or more days)",
            "Plants every 2–3 days in such weather",
        ),
        "Immediately when late blight is suspected: it spreads very fast and neighbouring growers should be warned.",
    ),
    E(
        "squash_powdery_mildew",
        "Powdery mildew of cucurbits",
        "Podosphaera xanthii (also Golovinomyces spp.)",
        "fungus",
        ("squash",),
        "A fungal disease forming white powder on squash and other cucurbit leaves.",
        ("White powdery spots on both leaf surfaces", "Leaves yellow, then turn brown and dry"),
        "The fungus grows on the leaf surface; spores blow in each season.",
        "Warm, dry days with humid nights; shade; dense planting. Rain is not needed.",
        "Wind-borne spores.",
        ("Remove the worst leaves", _FUNGICIDE),
        ("Resistant varieties", "Full sun and good spacing"),
        ("Sulphur, potassium bicarbonate or biological products where locally approved",),
        ("Leaf undersides from flowering onward",),
        "If it appears early, before fruit set.",
    ),
    E(
        "strawberry_leaf_scorch",
        "Strawberry leaf scorch",
        "Diplocarpon earlianum",
        "fungus",
        ("strawberry",),
        "A fungal leaf disease of strawberry.",
        ("Many small dark purple spots that merge", "Leaves look scorched and dry at the edges"),
        "The fungus survives on infected leaves.",
        "Warm, wet weather; long leaf wetness.",
        "Rain splash and overhead water.",
        ("Remove old infected leaves after harvest (renovation)", _FUNGICIDE),
        ("Use clean plants", "Drip irrigation", "Good spacing"),
        ("Renovation and drip irrigation",),
        ("Leaf spots in spring and after renovation",),
        "If plants are weakened before flowering.",
    ),
    E(
        "tomato_leaf_mold",
        "Tomato leaf mold",
        "Passalora fulva (Fulvia fulva)",
        "fungus",
        ("tomato",),
        "A fungal leaf disease of tomato, mainly in greenhouses and humid tunnels.",
        (
            "Pale yellow spots on the upper leaf surface",
            "Olive-green to brown velvety mould on the underside",
        ),
        "The fungus survives on debris and on greenhouse structures.",
        "Relative humidity above about 85 %, moderate temperatures, poor ventilation.",
        "Airborne spores, workers and tools.",
        ("Ventilate and lower humidity", "Remove infected leaves", _FUNGICIDE),
        ("Resistant varieties", "Wider spacing; avoid wetting leaves"),
        ("Climate control (ventilation) is the main control",),
        ("Greenhouse humidity", "Leaf undersides"),
        "If it spreads despite ventilation.",
    ),
    E(
        "septoria_leaf_spot",
        "Septoria leaf spot of tomato",
        "Septoria lycopersici",
        "fungus",
        ("tomato",),
        "A fungal leaf spot of tomato that strips plants from the bottom up.",
        (
            "Many small round spots with dark borders and grey centres",
            "Tiny black dots in the spot centres",
            "Lower leaves yellow and drop",
        ),
        "The fungus survives on tomato debris and on related weeds (nightshades).",
        "Warm, wet weather; long leaf wetness.",
        "Rain splash and overhead irrigation; hands and tools.",
        ("Remove infected lower leaves", "Mulch", _FUNGICIDE),
        (_ROTATE, "Control nightshade weeds", "Drip irrigation"),
        ("Mulch, rotation and sanitation",),
        ("Lower leaves after rain",),
        "If leaf loss reaches the middle of the plant.",
    ),
    E(
        "spider_mites",
        "Two-spotted spider mite (a pest, not a disease)",
        "Tetranychus urticae",
        "mite",
        ("tomato",),
        "Tiny mites that suck leaf cells. The model lists them among diseases, but they are a pest.",
        ("Fine pale speckling on leaves", "Fine webbing on leaf undersides", "Leaves turn bronze and dry"),
        "Mite numbers explode in hot, dry conditions, especially after broad-spectrum sprays kill their predators.",
        "Hot (above about 27 °C), dry, dusty conditions; drought-stressed plants.",
        "Mites crawl between touching plants and are carried by wind, people and tools.",
        (
            "Confirm with a hand lens on leaf undersides",
            "Spray water on leaf undersides to knock mites off",
            "Use a locally registered miticide only if needed; mites become resistant quickly",
        ),
        ("Avoid unnecessary broad-spectrum insecticides", "Keep plants well watered", "Reduce dust"),
        ("Conserve or release predatory mites (e.g. Phytoseiulus persimilis)",),
        ("Leaf undersides during hot, dry spells",),
        "If numbers keep rising after two weeks of action.",
    ),
    E(
        "target_spot",
        "Target spot of tomato",
        "Corynespora cassiicola",
        "fungus",
        ("tomato",),
        "A fungal leaf, stem and fruit spot of tomato in warm, humid regions.",
        ("Brown spots with concentric rings, similar to early blight", "Sunken spots on fruit"),
        "The fungus survives on debris and on many other host plants.",
        "Warm (about 20–28 °C), humid weather; dense canopies.",
        "Wind and rain splash.",
        ("Remove infected lower leaves", "Prune for airflow", _FUNGICIDE),
        (_ROTATE, "Avoid overhead irrigation"),
        ("Canopy management and rotation",),
        ("Lower leaves and fruit after humid weeks",),
        "To tell it apart from early blight if the treatment depends on it.",
    ),
    E(
        "tomato_yellow_leaf_curl_virus",
        "Tomato yellow leaf curl virus (TYLCV)",
        "Begomovirus (TYLCV)",
        "virus",
        ("tomato",),
        "A whitefly-transmitted virus. Infected plants stay stunted and set little fruit. There is no cure.",
        (
            "Small leaves curled upward and cupped, with yellow edges",
            "Stunted plants",
            "Flowers drop; few fruit",
        ),
        "The silverleaf whitefly (Bemisia tabaci) carries the virus.",
        "Warm weather with many whiteflies.",
        "Whiteflies feeding on infected plants then healthy ones; infected transplants. Not spread by seed or touch.",
        ("Remove and bag infected plants early", "Manage whiteflies (no product cures the virus)"),
        (
            "Resistant varieties",
            "Insect-proof netting in the nursery",
            "Whitefly-free transplants",
            "A crop-free period to break the cycle",
        ),
        ("Netting, yellow sticky traps, reflective mulch, conserving natural enemies",),
        ("Whitefly numbers on sticky traps", "Young plants for curling"),
        "If more than a few percent of plants are infected, to plan the next crop.",
    ),
    E(
        "tomato_mosaic_virus",
        "Tomato mosaic virus (ToMV / TMV)",
        "Tobamovirus",
        "virus",
        ("tomato",),
        "A very stable virus spread by touch. There is no cure.",
        ("Light and dark green mosaic on leaves", "Distorted, fern-like leaves", "Uneven ripening of fruit"),
        "The virus survives for a long time on seed, debris, tools and hands.",
        "Any conditions; it spreads through handling.",
        "Mechanical: hands, tools, clothing, plant contact; contaminated seed. Not by insects.",
        ("Remove infected plants", "Wash hands and disinfect tools between plants"),
        ("Resistant varieties", "Treated or certified seed", "No tobacco use near plants"),
        ("Hygiene and resistant varieties; no chemical control exists",),
        ("Mosaic on new leaves after plants are handled",),
        "For a lab test if fruit symptoms appear.",
    ),
    E(
        "rice_brown_spot",
        "Brown spot of rice",
        "Bipolaris oryzae (Cochliobolus miyabeanus)",
        "fungus",
        ("rice",),
        "A fungal disease of rice, strongly linked to poor soil fertility.",
        ("Oval brown spots with grey centres on leaves", "Dark spots on grains; poor grain filling"),
        "Carried on seed and residue; crops short of nutrients (especially potassium and silicon) or under drought stress are most affected.",
        "Warm (about 25–30 °C), humid weather; nutrient-poor soils.",
        "Infected seed and airborne spores.",
        ("Correct nutrient deficiencies based on a soil test", _FUNGICIDE),
        ("Use clean or treated seed", "Balanced fertilisation, especially potassium"),
        ("Fixing soil fertility is the long-term control",),
        ("Leaf spots from tillering onward", "Soil-test results for potassium"),
        "If spots appear on the panicles.",
    ),
    E(
        "rice_leaf_blast",
        "Rice blast",
        "Magnaporthe oryzae (Pyricularia oryzae)",
        "fungus",
        ("rice",),
        "One of the most damaging rice diseases; it can attack leaves, nodes and the panicle neck.",
        (
            "Diamond-shaped spots with grey centres and brown borders",
            "Neck blast: the panicle neck rots and grains stay empty",
        ),
        "The fungus survives on residue and seed; high nitrogen favours it.",
        "Long leaf wetness, high humidity, about 20–28 °C, cool nights; excess nitrogen.",
        "Airborne spores over long distances.",
        ("Split nitrogen into smaller doses", _FUNGICIDE),
        ("Resistant varieties", "Avoid excess nitrogen", "Clean seed"),
        ("Resistant varieties and balanced nitrogen",),
        ("Leaf spots during tillering", "The panicle neck at heading"),
        "At heading if leaf blast is present: neck blast can cause heavy losses.",
    ),
    E(
        "wheat_leaf_rust",
        "Wheat leaf (brown) rust",
        "Puccinia triticina",
        "fungus",
        ("wheat",),
        "A rust fungus producing orange-brown pustules on wheat leaves.",
        ("Small round orange-brown pustules scattered over the leaves", "Pustules rub off as rusty dust"),
        "Spores blow in from other wheat areas or survive on volunteer wheat.",
        "Moderate temperatures (about 15–22 °C) with dew.",
        "Wind-borne spores over long distances; a new generation every 7–10 days.",
        ("Use resistant varieties", _FUNGICIDE),
        ("Resistant varieties", "Remove volunteer wheat", "Timely sowing"),
        ("Variety resistance is the main control",),
        ("The flag leaf and the leaf below it, from booting",),
        "If pustules reach the flag leaf before flowering.",
    ),
    E(
        "wheat_stripe_rust",
        "Wheat yellow (stripe) rust",
        "Puccinia striiformis f. sp. tritici",
        "fungus",
        ("wheat",),
        "A rust fungus forming yellow stripes of pustules on wheat leaves; it can cause severe losses in cool regions.",
        ("Yellow-orange pustules in stripes along the leaf veins", "Leaves dry early"),
        "Spores blow in from other regions; it needs living wheat or grasses to survive.",
        "Cool (about 10–15 °C), moist weather; dew.",
        "Wind-borne spores over very long distances.",
        ("Resistant varieties", _FUNGICIDE),
        ("Resistant varieties", "Avoid very early sowing in risk areas"),
        ("Variety resistance; spray only when pustules appear in the crop",),
        ("Yellow patches in the field during cool weeks",),
        "As soon as stripes are seen in cool weather: it spreads quickly.",
    ),
)

BY_KEY = {e.key: e for e in ENTRIES}

# (crop, model disease label) -> knowledge key. Must cover every disease label of both installed models (tested).
LABEL_MAP: dict[tuple[str, str], str] = {
    ("apple", "Apple scab"): "apple_scab",
    ("apple", "Black rot"): "apple_black_rot",
    ("apple", "Cedar apple rust"): "cedar_apple_rust",
    ("cherry", "Powdery mildew"): "cherry_powdery_mildew",
    ("corn", "Gray leaf spot"): "gray_leaf_spot",
    ("corn", "Cercospora / gray leaf spot"): "gray_leaf_spot",
    ("corn", "Common rust"): "corn_common_rust",
    ("corn", "Northern leaf blight"): "northern_leaf_blight",
    ("grape", "Black rot"): "grape_black_rot",
    ("grape", "Esca (black measles)"): "grape_esca",
    ("grape", "Isariopsis leaf spot"): "grape_isariopsis_leaf_spot",
    ("orange", "Citrus greening (HLB)"): "citrus_greening",
    ("peach", "Bacterial spot"): "peach_bacterial_spot",
    ("bell pepper", "Bacterial spot"): "bacterial_spot",
    ("tomato", "Bacterial spot"): "bacterial_spot",
    ("potato", "Early blight"): "early_blight",
    ("tomato", "Early blight"): "early_blight",
    ("potato", "Late blight"): "late_blight",
    ("tomato", "Late blight"): "late_blight",
    ("squash", "Powdery mildew"): "squash_powdery_mildew",
    ("strawberry", "Leaf scorch"): "strawberry_leaf_scorch",
    ("tomato", "Leaf mold"): "tomato_leaf_mold",
    ("tomato", "Septoria leaf spot"): "septoria_leaf_spot",
    ("tomato", "Spider mites"): "spider_mites",
    ("tomato", "Target spot"): "target_spot",
    ("tomato", "Yellow leaf curl virus"): "tomato_yellow_leaf_curl_virus",
    ("tomato", "Mosaic virus"): "tomato_mosaic_virus",
    ("rice", "Brown spot"): "rice_brown_spot",
    ("rice", "Leaf blast"): "rice_leaf_blast",
    ("wheat", "Brown rust"): "wheat_leaf_rust",
    ("wheat", "Yellow (stripe) rust"): "wheat_stripe_rust",
}

HEALTHY_GUIDANCE: dict[str, Any] = {
    "what": "The model's top answer for this crop was its 'healthy' class. This is a screening result, not a guarantee.",
    "monitor": [
        "Re-check every 1–2 weeks, and after long wet or humid spells",
        "Look at leaf undersides and the lower canopy, where many diseases start",
        "Photograph a different leaf if symptoms appear",
    ],
    "prevention": [
        "Keep rotating crops and removing infected residue",
        "Water at the base (drip) rather than over the leaves",
        "Use clean seed and transplants",
    ],
    "seek_advice": SEEK_ADVICE_COMMON,
    "source": SOURCE,
    "reviewed": False,
}


def key_for(crop: str | None, disease: str | None) -> str | None:
    if not crop or not disease:
        return None
    return LABEL_MAP.get((crop, disease))


def key_for_label(label: str | None) -> str | None:
    """Stored labels look like 'Corn: Gray leaf spot' (see app.vision.disease.label_text)."""
    if not label or ":" not in label:
        return None
    crop, disease = (p.strip() for p in label.split(":", 1))
    return key_for(crop.lower(), disease)


def info(key: str | None) -> dict[str, Any] | None:
    e = BY_KEY.get(key or "")
    return e.to_dict() if e else None
