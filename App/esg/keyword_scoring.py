import logging
import re
from typing import Dict, List, Tuple
from django.db import transaction
from .models import ExtractedText, KeywordResult, ESGScore, ScoreBreakdown, Supplier

logger = logging.getLogger(__name__)

# Define ESG keywords with their categories and points
ESG_KEYWORDS = {
    "E": {  
        "environmental policy": 5,
        "carbon emissions": 5,
        "iso 14001": 8,
        "renewable energy": 6,
        "waste management": 4,
        "water conservation": 4,
        "climate change": 5,
        "sustainability": 4,
        "carbon footprint": 5,
        "greenhouse gas": 5,
    },
    "S": {  # Social
        "labour rights": 6,
        "human rights": 7,
        "health and safety": 6,
        "diversity and inclusion": 5,
        "employee welfare": 4,
        "fair wages": 5,
        "working conditions": 5,
        "child labor": 7,
        "supply chain responsibility": 6,
        "community engagement": 4,
    },
    "G": {  # Governance
        "anti-corruption": 7,
        "ethics policy": 6,
        "whistleblowing": 6,
        "governance structure": 5,
        "board independence": 5,
        "transparency": 5,
        "risk management": 5,
        "compliance": 5,
        "audit": 4,
        "stakeholder engagement": 4,
    }
}

# Maximum possible points per category
MAX_POINTS = {
    "E": sum(ESG_KEYWORDS["E"].values()),
    "S": sum(ESG_KEYWORDS["S"].values()),
    "G": sum(ESG_KEYWORDS["G"].values()),
}


def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def find_keywords_in_text(text: str) -> Dict[str, List[Tuple[str, bool, int]]]:
    normalized_text = normalize_text(text)
    results = {"E": [], "S": [], "G": []}
    
    for category, keywords in ESG_KEYWORDS.items():
        for keyword, points in keywords.items():
            # Use word boundary regex for more accurate matching
            pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
            found = bool(re.search(pattern, normalized_text))
            results[category].append((keyword, found, points if found else 0))
            
            if found:
                logger.info(f"Found keyword '{keyword}' in category {category}")
    
    return results


def calculate_category_scores(keyword_results: Dict[str, List[Tuple[str, bool, int]]]) -> Dict[str, int]:
    category_scores = {}
    
    for category, results in keyword_results.items():
        total_points = sum(points for _, _, points in results)
        category_scores[category] = total_points
        logger.info(f"Category {category}: {total_points}/{MAX_POINTS[category]} points")
    
    return category_scores


def calculate_total_score(category_scores: Dict[str, int]) -> int:
    env_percentage = (category_scores["E"] / MAX_POINTS["E"]) * 100 if MAX_POINTS["E"] > 0 else 0
    social_percentage = (category_scores["S"] / MAX_POINTS["S"]) * 100 if MAX_POINTS["S"] > 0 else 0
    gov_percentage = (category_scores["G"] / MAX_POINTS["G"]) * 100 if MAX_POINTS["G"] > 0 else 0
    
    # Weighted average
    total = (env_percentage * 0.35) + (social_percentage * 0.35) + (gov_percentage * 0.30)
    
    return int(round(total))


def determine_risk_level(total_score: int) -> str:
    if total_score >= 70:
        return "LOW"
    elif total_score >= 40:
        return "MEDIUM"
    else:
        return "HIGH"


@transaction.atomic
def process_keywords_and_score(extraction: ExtractedText) -> ESGScore:
    logger.info(f"Processing keywords for extraction ID: {extraction.id}")
    
    keyword_results = find_keywords_in_text(extraction.raw_text)
    
    for category, results in keyword_results.items():
        for keyword, found, points in results:
            KeywordResult.objects.create(
                extraction=extraction,
                esg_category=category,
                keyword=keyword,
                found=found,
                points_awarded=points
            )
    
    logger.info(f"Saved {sum(len(r) for r in keyword_results.values())} keyword results")
    category_scores = calculate_category_scores(keyword_results)
    
    total_score = calculate_total_score(category_scores)
    
    risk_level = determine_risk_level(total_score)
    
    logger.info(f"Total score: {total_score}, Risk level: {risk_level}")

    supplier = extraction.document.supplier
    esg_score, created = ESGScore.objects.update_or_create(
        supplier=supplier,
        defaults={
            "total_score": total_score,
            "risk_level": risk_level,
            "env_points": category_scores["E"],
            "social_points": category_scores["S"],
            "governance_points": category_scores["G"],
        }
    )
    
    create_score_breakdown(esg_score, keyword_results)
    
    supplier.esg_score = total_score
    supplier.risk_level = risk_level
    supplier.save(update_fields=["esg_score", "risk_level"])
    logger.info(f"ESG Score {'created' if created else 'updated'} for supplier: {supplier.name}")
    
    return esg_score


def create_score_breakdown(esg_score: ESGScore, keyword_results: Dict[str, List[Tuple[str, bool, int]]]):
    """Create detailed breakdown of score factors."""

    ScoreBreakdown.objects.filter(score=esg_score).delete()
    
    breakdown_items = []
    
    for keyword, found, points in keyword_results["E"]:
        if found:
            max_pts = ESG_KEYWORDS["E"][keyword]
            breakdown_items.append(
                ScoreBreakdown(
                    score=esg_score,
                    factor_name=f"Environmental - {keyword.title()}",
                    max_points=max_pts,
                    earned_points=points,
                    achieved=True
                )
            )
    
    for keyword, found, points in keyword_results["S"]:
        if found:
            max_pts = ESG_KEYWORDS["S"][keyword]
            breakdown_items.append(
                ScoreBreakdown(
                    score=esg_score,
                    factor_name=f"Social - {keyword.title()}",
                    max_points=max_pts,
                    earned_points=points,
                    achieved=True
                )
            )
    
    for keyword, found, points in keyword_results["G"]:
        if found:
            max_pts = ESG_KEYWORDS["G"][keyword]
            breakdown_items.append(
                ScoreBreakdown(
                    score=esg_score,
                    factor_name=f"Governance - {keyword.title()}",
                    max_points=max_pts,
                    earned_points=points,
                    achieved=True
                )
            )
    
    ScoreBreakdown.objects.bulk_create(breakdown_items)
    logger.info(f"Created {len(breakdown_items)} score breakdown items")


def recalculate_supplier_score(supplier: Supplier) -> ESGScore:
    logger.info(f"Recalculating score for supplier: {supplier.name}")
    
    extractions = ExtractedText.objects.filter(
        document__supplier=supplier
    ).select_related('document')
    
    if not extractions.exists():
        logger.warning(f"No extractions found for supplier: {supplier.name}")
        return None
    
    all_keyword_results = {"E": [], "S": [], "G": []}
    
    for extraction in extractions:
        keyword_results = find_keywords_in_text(extraction.raw_text)
    
        for category in ["E", "S", "G"]:
            all_keyword_results[category].extend(keyword_results[category])
    
    for category in ["E", "S", "G"]:
        unique_keywords = {}
        for keyword, found, points in all_keyword_results[category]:
            if keyword not in unique_keywords:
                unique_keywords[keyword] = (keyword, found, points)
            elif found:
                unique_keywords[keyword] = (keyword, True, ESG_KEYWORDS[category][keyword])
        
        all_keyword_results[category] = list(unique_keywords.values())
    
    category_scores = calculate_category_scores(all_keyword_results)
    total_score = calculate_total_score(category_scores)
    risk_level = determine_risk_level(total_score)
    
    esg_score, _ = ESGScore.objects.update_or_create(
        supplier=supplier,
        defaults={
            "total_score": total_score,
            "risk_level": risk_level,
            "env_points": category_scores["E"],
            "social_points": category_scores["S"],
            "governance_points": category_scores["G"],
        }
    )
    
    supplier.esg_score = total_score
    supplier.risk_level = risk_level
    supplier.save(update_fields=["esg_score", "risk_level"])
    
    return esg_score