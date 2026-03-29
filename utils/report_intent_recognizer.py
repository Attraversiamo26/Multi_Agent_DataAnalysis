"""
Report Intent Recognition System
用于智能识别用户是否需要生成完整报告的关键词识别系统
"""
import logging
import re
from typing import List, Dict, Tuple, Optional, Set
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class KeywordMatch:
    """关键词匹配结果"""
    keyword: str
    matched_text: str
    position: int
    confidence: float  # 0.0 - 1.0
    category: str


@dataclass
class ReportIntentResult:
    """报告意图识别结果"""
    should_generate_report: bool
    matched_keywords: List[KeywordMatch] = field(default_factory=list)
    confidence_score: float = 0.0
    decision_reason: str = ""
    complexity_indicators: Dict[str, Any] = field(default_factory=dict)


class ReportIntentRecognizer:
    """报告意图识别器"""
    
    def __init__(self):
        self._init_keyword_libraries()
        self._init_synonym_maps()
        self._init_context_patterns()
        
    def _init_keyword_libraries(self):
        """初始化关键词库"""
        
        self.core_report_keywords = {
            "zh": [
                "报告", "分析报告", "生成报告", "完整报告", "综合报告",
                "详细报告", "深度分析", "全面分析", "总结报告", "分析总结",
                "深度剖析", "全面剖析"
            ],
            "en": [
                "report", "analysis report", "generate report", "complete report",
                "comprehensive report", "detailed report", "in-depth analysis",
                "full analysis", "summary report", "analysis summary"
            ]
        }
        
        self.analysis_keywords = {
            "zh": [
                "分析", "深入分析", "数据分析", "趋势分析", "对比分析",
                "洞察", "见解", "发现", "结论", "建议", "推荐"
            ],
            "en": [
                "analyze", "analysis", "in-depth analysis", "data analysis",
                "trend analysis", "comparative analysis", "insight", "finding",
                "conclusion", "suggestion", "recommendation"
            ]
        }
        
        self.anti_patterns = {
            "zh": [
                "只需要数据", "只要数据", "仅数据", "不用分析", "不要报告",
                "直接给数据", "看数据就行", "数据即可", "不需要分析",
                "不做分析", "不要分析"
            ],
            "en": [
                "only data", "just data", "data only", "no analysis",
                "no report", "give me data directly", "just show data"
            ]
        }
        
        self.complexity_indicators = {
            "zh": [
                "为什么", "原因", "因素", "影响", "关系", "对比", "比较",
                "趋势", "变化", "增长", "下降", "模式", "规律"
            ],
            "en": [
                "why", "reason", "factor", "impact", "relationship", "compare",
                "comparison", "trend", "change", "growth", "decline", "pattern"
            ]
        }
    
    def _init_synonym_maps(self):
        """初始化同义词映射"""
        
        self.synonym_map = {
            "报告": ["分析报告", "完整报告", "综合报告", "总结报告"],
            "分析": ["深入分析", "全面分析", "数据分析"],
            "建议": ["推荐", "意见"],
            "结论": ["总结", "结果"],
            "report": ["analysis report", "comprehensive report", "summary report"],
            "analyze": ["analysis", "in-depth analysis"],
            "recommendation": ["suggestion", "advice"],
            "conclusion": ["summary", "finding"]
        }
    
    def _init_context_patterns(self):
        """初始化上下文模式"""
        
        self.context_patterns = [
            (re.compile(r'请[给为](我|我们).*报告', re.IGNORECASE), 0.9),
            (re.compile(r'需要.*报告', re.IGNORECASE), 0.85),
            (re.compile(r'想要.*报告', re.IGNORECASE), 0.85),
            (re.compile(r'分析一下', re.IGNORECASE), 0.8),
            (re.compile(r'帮我分析', re.IGNORECASE), 0.8),
            (re.compile(r'could you.*report', re.IGNORECASE), 0.9),
            (re.compile(r'please.*report', re.IGNORECASE), 0.85),
            (re.compile(r'i need.*report', re.IGNORECASE), 0.85),
            (re.compile(r'i want.*report', re.IGNORECASE), 0.85),
        ]
    
    def _detect_language(self, text: str) -> str:
        """检测文本语言"""
        chinese_chars = re.findall(r'[\u4e00-\u9fff]', text)
        english_chars = re.findall(r'[a-zA-Z]', text)
        
        if len(chinese_chars) > len(english_chars):
            return "zh"
        return "en"
    
    def _match_keywords(
        self, 
        text: str, 
        keywords: List[str], 
        category: str,
        base_confidence: float = 0.8
    ) -> List[KeywordMatch]:
        """匹配关键词"""
        matches = []
        text_lower = text.lower()
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in text_lower:
                position = text_lower.find(keyword_lower)
                
                confidence = base_confidence
                if len(keyword) >= 4:
                    confidence += 0.1
                
                matches.append(KeywordMatch(
                    keyword=keyword,
                    matched_text=text[position:position+len(keyword)],
                    position=position,
                    confidence=min(confidence, 1.0),
                    category=category
                ))
        
        return matches
    
    def _match_context_patterns(self, text: str) -> List[KeywordMatch]:
        """匹配上下文模式"""
        matches = []
        
        for pattern, confidence in self.context_patterns:
            match_result = pattern.search(text)
            if match_result:
                matches.append(KeywordMatch(
                    keyword=match_result.group(0),
                    matched_text=match_result.group(0),
                    position=match_result.start(),
                    confidence=confidence,
                    category="context_pattern"
                ))
        
        return matches
    
    def _check_anti_patterns(self, text: str, language: str) -> Tuple[bool, float]:
        """检查反模式（明确不需要报告）"""
        anti_keywords = self.anti_patterns.get(language, [])
        text_lower = text.lower()
        
        for keyword in anti_keywords:
            if keyword.lower() in text_lower:
                return True, 0.9
        
        return False, 0.0
    
    def _calculate_complexity_score(
        self,
        text: str,
        executed_steps: int,
        chart_count: int,
        language: str
    ) -> Dict[str, Any]:
        """计算复杂度指标"""
        complexity_indicators = {
            "step_count": executed_steps,
            "chart_count": chart_count,
            "has_complex_keywords": False,
            "complex_keyword_count": 0
        }
        
        complexity_keywords = self.complexity_indicators.get(language, [])
        text_lower = text.lower()
        
        for keyword in complexity_keywords:
            if keyword.lower() in text_lower:
                complexity_indicators["has_complex_keywords"] = True
                complexity_indicators["complex_keyword_count"] += 1
        
        return complexity_indicators
    
    def _expand_with_synonyms(self, keywords: List[str]) -> Set[str]:
        """使用同义词扩展关键词"""
        expanded = set(keywords)
        
        for keyword in keywords:
            if keyword in self.synonym_map:
                expanded.update(self.synonym_map[keyword])
        
        return expanded
    
    def recognize(
        self,
        user_question: str,
        executed_steps: Optional[int] = None,
        chart_count: Optional[int] = None
    ) -> ReportIntentResult:
        """
        主识别函数
        
        Args:
            user_question: 用户问题
            executed_steps: 已执行步骤数
            chart_count: 生成的图表数
        
        Returns:
            ReportIntentResult: 识别结果
        """
        language = self._detect_language(user_question)
        
        all_matches: List[KeywordMatch] = []
        
        has_anti_pattern, anti_confidence = self._check_anti_patterns(user_question, language)
        
        if has_anti_pattern:
            return ReportIntentResult(
                should_generate_report=False,
                matched_keywords=[],
                confidence_score=anti_confidence,
                decision_reason="检测到明确的反模式关键词，用户明确表示不需要报告"
            )
        
        report_keywords = self.core_report_keywords.get(language, [])
        analysis_keywords = self.analysis_keywords.get(language, [])
        
        all_matches.extend(
            self._match_keywords(user_question, report_keywords, "core_report", 0.9)
        )
        all_matches.extend(
            self._match_keywords(user_question, analysis_keywords, "analysis", 0.75)
        )
        
        all_matches.extend(self._match_context_patterns(user_question))
        
        complexity_indicators = self._calculate_complexity_score(
            user_question,
            executed_steps or 0,
            chart_count or 0,
            language
        )
        
        should_generate_report = False
        confidence_score = 0.0
        decision_reason = ""
        
        if all_matches:
            max_confidence = max(m.confidence for m in all_matches)
            should_generate_report = True
            confidence_score = max_confidence
            decision_reason = f"检测到报告相关关键词（最高置信度: {max_confidence:.2f}）"
        elif complexity_indicators["has_complex_keywords"]:
            should_generate_report = True
            confidence_score = 0.5
            decision_reason = f"检测到{complexity_indicators['complex_keyword_count']}个复杂度关键词"
        else:
            should_generate_report = False
            confidence_score = 0.7
            decision_reason = "未检测到报告意图关键词，且分析复杂度较低"
        
        result = ReportIntentResult(
            should_generate_report=should_generate_report,
            matched_keywords=all_matches,
            confidence_score=confidence_score,
            decision_reason=decision_reason,
            complexity_indicators=complexity_indicators
        )
        
        self._log_decision(result, user_question)
        
        return result
    
    def _log_decision(self, result: ReportIntentResult, user_question: str):
        """记录决策日志"""
        logger.info(
            f"Report Intent Decision: "
            f"should_generate_report={result.should_generate_report}, "
            f"confidence={result.confidence_score:.2f}, "
            f"reason='{result.decision_reason}', "
            f"question='{user_question[:100]}...'"
        )
        
        if result.matched_keywords:
            logger.debug(
                f"Matched keywords: {[(m.keyword, m.category, m.confidence) for m in result.matched_keywords]}"
            )
        
        if result.complexity_indicators:
            logger.debug(f"Complexity indicators: {result.complexity_indicators}")


def create_report_intent_recognizer() -> ReportIntentRecognizer:
    """创建报告意图识别器实例"""
    return ReportIntentRecognizer()
