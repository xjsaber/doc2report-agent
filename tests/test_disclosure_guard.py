import pytest

from core.graph.disclosure_guard import correct_disclosure_denials

STRUCTURE = '检索片段未包含分部报告或分行业、分地区收入明细[a.pdf p18]；分部收入结构【待核实】。'
MARGIN = ('分行业表中，物联网行业营业收入为521,803,949.48元，营业成本为305,205,137.94元 '
          '[a.pdf p18]；该片段未完整显示对应毛利率及同比增减数值，毛利率相关结论【待核实】[a.pdf p18]。')
TABLE = ('营业收入\n营业成本\n毛利率\n分行业\n物联网行业\n'
         '521,803,949.48\n305,205,137.94\n41.51%\n-8.87%\n-12.13%\n2.17%')

def hit(text, file='a.pdf', page=18):
    return dict(file=file, page=page, text=text, chunk_id='c18', doc_id='d', score=1.0, section='主营业务')


def test_structure_denial_corrected_only_with_actual_labeled_rows():
    text='分行业\n物联网行业\n521,803,949.48\n分地区\n国内\n393,170,959.85'
    corrected, notes = correct_disclosure_denials(STRUCTURE, [hit(text)])
    assert corrected == '引用片段列示了分行业、分地区收入明细[a.pdf p18]。'
    assert notes


@pytest.mark.parametrize('text', ['分行业\n分地区', '分行业\n物联网行业\n521,803,949.48',
                                  '分行业\n未披露\n分地区\n未披露'])
def test_incomplete_structure_evidence_preserves_pending(text):
    assert correct_disclosure_denials(STRUCTURE, [hit(text)]) == (STRUCTURE, [])


def test_margin_denial_corrected_but_unchecked_yoy_stays_pending():
    corrected, notes = correct_disclosure_denials(MARGIN, [hit(TABLE)])
    assert '毛利率为41.51%' in corrected
    assert '未完整显示' not in corrected
    assert '同比增减数值仍需核对【待核实】' in corrected
    assert notes


@pytest.mark.parametrize('text', [TABLE.replace('41.51%', ''), TABLE.replace('41.51%', '95.62%'),
                                  TABLE.replace('物联网行业', '其他行业'), TABLE.replace('毛利率', '')])
def test_missing_misaligned_or_inconsistent_margin_keeps_warning(text):
    assert correct_disclosure_denials(MARGIN, [hit(text)]) == (MARGIN, [])


def test_separate_chunks_do_not_fabricate_complete_margin_row():
    parts=TABLE.split('41.51%')
    assert correct_disclosure_denials(MARGIN, [hit(parts[0]), hit('41.51%'+parts[1])]) == (MARGIN, [])


@pytest.mark.parametrize('source', [hit(TABLE, page=19), hit(TABLE, file='other.pdf')])
def test_unrelated_citation_never_repairs_denial(source):
    assert correct_disclosure_denials(MARGIN, [source]) == (MARGIN, [])


def test_real_missing_product_and_annual_cashflow_warnings_unchanged():
    original=('主要产品/服务构成【待核实】[a.pdf p18]。'
              '片段未提供全年经营活动现金流量净额及资产负债率等指标，相关分析【待核实】。')
    assert correct_disclosure_denials(original, [hit(TABLE)]) == (original, [])


def test_graph_applies_guard_before_numeric_verification():
    from core.graph.workflow import build_report_graph
    from core.models import SearchHit
    class Retriever:
        def search(self, *args, **kwargs):
            return [SearchHit(**hit(TABLE))]
    class Writer:
        def complete(self, messages):
            return MARGIN
    state=build_report_graph(retriever=Retriever(), chat_model=Writer(), top_k=1).invoke(
        dict(template_id='company_analysis', title='测试', doc_ids=['d'], sections=[], errors=[]))
    assert '未完整显示对应毛利率' not in state['report_md']
    assert '毛利率为41.51%' in state['report_md']
    assert '同比增减数值仍需核对【待核实】' in state['report_md']
    assert all(s['verification_status']=='supported' for s in state['sections'])
    assert all(any('disclosure_guard:' in n for n in s['verification_notes']) for s in state['sections'])
