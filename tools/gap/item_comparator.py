"""
Item Comparator - Equipment evaluation and upgrade decisions

Compares weapons and armor to determine upgrades based on stats.
"""

import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)


class ItemComparator:
    """
    Compares equipment items to determine if an upgrade is worthwhile.

    Works with CharacterProfile to make class-appropriate decisions.
    """

    def __init__(self, profile=None):
        """
        Initialize comparator with character profile for context.

        Args:
            profile: CharacterProfile instance (optional, but recommended)
        """
        self.profile = profile

    def compare_weapons(self, current: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two weapons and determine if upgrade is worthwhile.

        Args:
            current: Currently equipped weapon dict with stats
            candidate: Candidate weapon dict with stats

        Returns:
            {
                "upgrade": bool,
                "score_diff": float,  # Positive = upgrade, negative = downgrade
                "reason": str,
            }
        """
        # Handle unequipped case (no current weapon)
        if not current or not current.get("stats"):
            return {
                "upgrade": True,
                "score_diff": 999.0,
                "reason": "No weapon equipped - equip this one"
            }

        # Both must be identified to compare
        if not candidate.get("stats"):
            return {
                "upgrade": False,
                "score_diff": 0.0,
                "reason": "Candidate not identified - cannot compare"
            }

        current_stats = current["stats"]
        candidate_stats = candidate["stats"]

        # Calculate weapon scores
        current_score = self._score_weapon(current_stats, current.get("type", "sw"))
        candidate_score = self._score_weapon(candidate_stats, candidate.get("type", "sw"))

        score_diff = candidate_score - current_score

        # Threshold: must be at least 10% better to be worth upgrading
        threshold = current_score * 0.10

        # Quality matters: unique/magic items have extra value
        quality_bonus = 0.0
        if candidate.get("quality") == "unique":
            quality_bonus = 5.0
        elif candidate.get("quality") == "magic":
            quality_bonus = 2.0

        # Check if upgrade passes threshold
        is_upgrade = (score_diff + quality_bonus) >= threshold

        reason = self._generate_weapon_comparison_reason(
            current, candidate, current_score, candidate_score, is_upgrade
        )

        return {
            "upgrade": is_upgrade,
            "score_diff": score_diff,
            "reason": reason
        }

    def _score_weapon(self, stats: Dict[str, Any], weapon_type: str) -> float:
        """
        Calculate numeric score for weapon based on stats.

        Score = avg_damage * (1 + to_hit/100)
        """
        min_dam = stats.get("min_dam", 0)
        max_dam = stats.get("max_dam", 0)
        dam_bonus = stats.get("dam_bonus", 0)
        to_hit = stats.get("to_hit", 0)

        # Average damage (including bonus)
        avg_damage = (min_dam + max_dam) / 2.0
        avg_damage = avg_damage * (100 + dam_bonus) / 100.0

        # ToHit contributes to score (more consistent hits = more damage)
        tohit_mult = 1.0 + (to_hit / 100.0)

        # Base score
        score = avg_damage * tohit_mult

        # Class-specific bias: reward the class weapon AND penalize off-class
        # weapons, so she keeps her bow (Rogue) / blade (Warrior) unless an
        # off-class weapon is *dramatically* better. Without the penalty a plain
        # higher-damage Scimitar out-scores a Rogue's bow and she ditches her
        # whole ranged identity.
        if self.profile:
            if self.profile.is_ranged:
                score *= 1.5 if weapon_type == "bw" else 0.6
            elif self.profile.is_melee:
                if weapon_type in ["sw", "ax", "mc"]:
                    score *= 1.3
                elif weapon_type == "bw":
                    score *= 0.8  # warriors can use bows but prefer melee
            elif self.profile.is_caster and weapon_type == "st":
                score *= 1.3

        return score

    def _generate_weapon_comparison_reason(
        self,
        current: Dict[str, Any],
        candidate: Dict[str, Any],
        current_score: float,
        candidate_score: float,
        is_upgrade: bool
    ) -> str:
        """Generate human-readable comparison reason"""
        current_stats = current["stats"]
        candidate_stats = candidate["stats"]

        current_avg_dam = (current_stats["min_dam"] + current_stats["max_dam"]) / 2.0
        candidate_avg_dam = (candidate_stats["min_dam"] + candidate_stats["max_dam"]) / 2.0

        if is_upgrade:
            dam_diff = candidate_avg_dam - current_avg_dam
            tohit_diff = candidate_stats["to_hit"] - current_stats["to_hit"]
            return f"UPGRADE: {candidate['type']} ({candidate_avg_dam:.1f} avg dam, +{candidate_stats['to_hit']} ToHit) vs {current['type']} ({current_avg_dam:.1f} avg dam, +{current_stats['to_hit']} ToHit) [{dam_diff:+.1f} dam, {tohit_diff:+d} ToHit]"
        else:
            return f"KEEP CURRENT: {current['type']} better than {candidate['type']} (score {current_score:.1f} vs {candidate_score:.1f})"

    def compare_armor(self, current: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare two armor pieces and determine if upgrade is worthwhile.

        Args:
            current: Currently equipped armor dict with stats
            candidate: Candidate armor dict with stats

        Returns:
            {
                "upgrade": bool,
                "score_diff": float,
                "reason": str,
            }
        """
        # Handle unequipped case
        if not current or not current.get("stats"):
            return {
                "upgrade": True,
                "score_diff": 999.0,
                "reason": "No armor equipped - equip this one"
            }

        # Both must be identified to compare
        if not candidate.get("stats"):
            return {
                "upgrade": False,
                "score_diff": 0.0,
                "reason": "Candidate not identified - cannot compare"
            }

        current_stats = current["stats"]
        candidate_stats = candidate["stats"]

        # Calculate armor scores
        current_score = self._score_armor(current_stats)
        candidate_score = self._score_armor(candidate_stats)

        score_diff = candidate_score - current_score

        # Threshold: must be at least 8% better (armor upgrades are more incremental)
        threshold = current_score * 0.08

        # Quality bonus
        quality_bonus = 0.0
        if candidate.get("quality") == "unique":
            quality_bonus = 3.0
        elif candidate.get("quality") == "magic":
            quality_bonus = 1.5

        is_upgrade = (score_diff + quality_bonus) >= threshold

        reason = self._generate_armor_comparison_reason(
            current, candidate, current_score, candidate_score, is_upgrade
        )

        return {
            "upgrade": is_upgrade,
            "score_diff": score_diff,
            "reason": reason
        }

    def _score_armor(self, stats: Dict[str, Any]) -> float:
        """
        Calculate numeric score for armor based on stats.

        Score = AC + (stat_bonus * multiplier)
        """
        ac = stats.get("ac", 0)
        stat_bonus = stats.get("stat_bonus", 0)

        # Base score from AC
        score = float(ac)

        # Stat bonuses are valuable (1 stat point ~ 2 AC value)
        score += abs(stat_bonus) * 2.0

        # Class-specific stat preferences
        if self.profile and stat_bonus != 0:
            # Warriors value Str/Vit
            if self.profile.is_melee:
                score += abs(stat_bonus) * 0.5  # Extra value for any stat
            # Rogues value Dex
            elif self.profile.is_ranged:
                score += abs(stat_bonus) * 0.3
            # Sorcerers value Mag
            elif self.profile.is_caster:
                score += abs(stat_bonus) * 0.4

        return score

    def _generate_armor_comparison_reason(
        self,
        current: Dict[str, Any],
        candidate: Dict[str, Any],
        current_score: float,
        candidate_score: float,
        is_upgrade: bool
    ) -> str:
        """Generate human-readable armor comparison reason"""
        current_stats = current["stats"]
        candidate_stats = candidate["stats"]

        if is_upgrade:
            ac_diff = candidate_stats["ac"] - current_stats["ac"]
            bonus_diff = candidate_stats["stat_bonus"] - current_stats["stat_bonus"]
            return f"UPGRADE: {candidate['type']} ({candidate_stats['ac']} AC, +{candidate_stats['stat_bonus']} stat) vs {current['type']} ({current_stats['ac']} AC, +{current_stats['stat_bonus']} stat) [{ac_diff:+d} AC, {bonus_diff:+d} stat]"
        else:
            return f"KEEP CURRENT: {current['type']} better than {candidate['type']} (score {current_score:.1f} vs {candidate_score:.1f})"

    def find_upgrades(self, state: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Scan inventory for potential equipment upgrades.

        Args:
            state: Parsed DSL state with inventory and equipped items

        Returns:
            List of upgrade recommendations:
            [
                {
                    "slot": "hand_left",
                    "current": {...},
                    "candidate": {...},
                    "upgrade_info": {...},  # Result from compare_weapons/armor
                },
                ...
            ]
        """
        upgrades = []
        equipped = state.get("equipped", {})
        inventory = state.get("inventory", [])

        # Weapons: treat as a SINGLE primary slot. Comparing hand_left and
        # hand_right independently makes an empty off-hand — which a two-handed
        # bow or a shield-less hand leaves open — look like it needs *any* weapon,
        # so she flip-flops her gear every tick. Compare candidates against the
        # one weapon she's actually wielding instead.
        current_weapon = equipped.get("hand_left") or equipped.get("hand_right")
        weapon_types = ["sw", "ax", "bw", "mc", "st"]
        weapon_candidates = [
            item for item in inventory
            if item["type"] in weapon_types and item.get("identified", False)
        ]
        for candidate in weapon_candidates:
            comparison = self.compare_weapons(current_weapon, candidate)
            if comparison["upgrade"]:
                upgrades.append({
                    "slot": "hand_left",
                    "current": current_weapon,
                    "candidate": candidate,
                    "upgrade_info": comparison,
                })

        # Check armor (chest)
        current_armor = equipped.get("chest")
        armor_types = ["la", "ma", "ha"]
        armor_candidates = [
            item for item in inventory
            if item["type"] in armor_types and item.get("identified", False)
        ]

        for candidate in armor_candidates:
            comparison = self.compare_armor(current_armor, candidate)
            if comparison["upgrade"]:
                upgrades.append({
                    "slot": "chest",
                    "current": current_armor,
                    "candidate": candidate,
                    "upgrade_info": comparison,
                })

        # Check helm (head)
        current_helm = equipped.get("head")
        helm_candidates = [
            item for item in inventory
            if item["type"] == "hl" and item.get("identified", False)
        ]

        for candidate in helm_candidates:
            comparison = self.compare_armor(current_helm, candidate)
            if comparison["upgrade"]:
                upgrades.append({
                    "slot": "head",
                    "current": current_helm,
                    "candidate": candidate,
                    "upgrade_info": comparison,
                })

        # Sort by score_diff (biggest upgrades first)
        upgrades.sort(key=lambda x: x["upgrade_info"]["score_diff"], reverse=True)

        return upgrades
