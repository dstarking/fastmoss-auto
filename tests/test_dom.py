"""Execute production browser scripts on DOM fixtures, including selection traps."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest
from fastmoss_auto.schema import PRODUCT_EXTRACT_JS, parse_product
from fastmoss_auto.collector import FILTER_JS, SALES_BOARD_JS


def evaluate(html, script):
    node = shutil.which('node')
    if not node:
        pytest.skip('Node.js needed for DOM fixtures')
    env = dict(os.environ)
    modules = Path('.dom-tests/node_modules').resolve()
    env['NODE_PATH'] = str(modules) + os.pathsep + env.get('NODE_PATH', '')
    code = r'''const fs = require('fs');
const {JSDOM} = require('jsdom');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const dom = new JSDOM(input.html, {url:'https://www.fastmoss.com/zh/e-commerce/sales-fixture', runScripts:'outside-only'});
dom.window.HTMLElement.prototype.getClientRects = function() { return this.style.display === 'none' ? [] : [{}]; };
Promise.resolve(dom.window.eval(input.script)).then(value => process.stdout.write(value)).catch(error => { console.error(error); process.exitCode=1; });'''
    result = subprocess.run([node, '-e', code], input=json.dumps({'html': html, 'script': script}), text=True, encoding='utf-8',
                            capture_output=True, env=env, timeout=15)
    if result.returncode and "Cannot find module 'jsdom'" in result.stderr:
        pytest.skip('Install jsdom@26.1.0 in .dom-tests for DOM fixtures')
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_extract_real_links_images_header_grid():
    html = '''<div class="ant-table-wrapper"><table><thead>
      <tr><th rowspan="2">排名</th><th rowspan="2">商品信息</th><th rowspan="2">国家/地区</th><th rowspan="2">类目</th><th colspan="2">昨日</th><th rowspan="2">店铺</th></tr>
      <tr><th>销量</th><th>销售额</th></tr></thead><tbody><tr>
      <td>1</td><td><a href="/zh/e-commerce/detail/123" title="完整商品标题">截断标题</a><img width="80" src="https://cdn.example.com/main.webp"></td>
      <td><img alt="Singapore" src="/flags/SG.png"></td><td>宠物用品 / 猫玩具</td><td>200</td><td>S$1000</td>
      <td><a href="/zh/shop-marketing/detail/999">Shop</a><img width="80" src="https://cdn.example.com/shop.png"></td>
      </tr></tbody></table></div>'''
    data = evaluate(html, PRODUCT_EXTRACT_JS)
    assert data['headers'] == ['排名', '商品信息', '国家/地区', '类目', '销量', '销售额', '店铺']
    row = parse_product(data['headers'], data['rows'][0], data['country_evidence'][0], lambda c: None)
    assert row['sales_period'] == '200' and row['category'] == '宠物用品 / 猫玩具'
    metadata = data['product_metadata'][0]
    assert metadata['product_title'] == '完整商品标题'
    assert metadata['product_id'] == '123'
    assert metadata['product_url'] == 'https://www.fastmoss.com/zh/e-commerce/detail/123'
    assert metadata['main_image_url'] == 'https://cdn.example.com/main.webp'
    assert 'SG' in data['country_evidence'][0]


def test_category_table_text_and_active_container_not_selection():
    html = '<div class="active"><span>全部</span><span>宠物用品</span></div><table><tr><td><span class="selected">宠物用品</span></td></tr></table>'
    assert not evaluate(html, FILTER_JS % (json.dumps('宠物用品'), '"check"'))['selected']
    assert not evaluate('<table><tr><td>宠物用品</td></tr></table>', FILTER_JS % (json.dumps('宠物用品'), '"check"'))['found']
    assert evaluate('<span class="selected">宠物用品</span>', FILTER_JS % (json.dumps('宠物用品'), '"check"'))['selected']


def test_sales_board_link_discovery_rejects_detail_and_ambiguity():
    html = '<a href="/zh/e-commerce/sales-fixture">商品销量榜</a><a href="/zh/e-commerce/newProducts">新品榜</a><table><tr><td><a href="/zh/e-commerce/detail/123">销量榜</a></td></tr></table>'
    assert evaluate(html, SALES_BOARD_JS)['url'].endswith('/sales-fixture')
    assert not evaluate(html + '<a href="/zh/e-commerce/other">销量榜</a>', SALES_BOARD_JS)['url']


def test_category_cell_tooltip_preserves_full_hierarchy():
    html = '<table><thead><tr><th>商品</th><th>国家</th><th>品类</th><th>销量</th><th>店铺</th></tr></thead><tbody><tr><td>Toy</td><td>SG</td><td title="宠物用品 / 猫用品 / 猫砂盆、猫厕所">猫砂盆、猫厕所</td><td>20</td><td>Shop</td></tr></tbody></table>'
    data = evaluate(html, PRODUCT_EXTRACT_JS)
    assert data['rows'][0][2] == '猫砂盆、猫厕所'
    assert data['product_metadata'][0]['category_paths'] == ['宠物用品 / 猫用品 / 猫砂盆、猫厕所']


def test_category_tree_reads_real_component_options():
    from fastmoss_auto.categories import CATEGORY_TREE_JS
    script = "document.querySelector('span').__reactProps$fixture = {options:[{label:'宠物用品', value:1, children:[{label:'猫砂盆、猫厕所',value:2}]}]};\n" + CATEGORY_TREE_JS % json.dumps('宠物用品')
    data = evaluate('<span>宠物用品</span>', script)
    assert data['trees'][0][0]['children'][0]['label'] == '猫砂盆、猫厕所'


def test_detail_category_evidence_excludes_navigation_and_product_title():
    from fastmoss_auto.categories import DETAIL_CATEGORY_JS
    html = '<nav class="category">美妆 / 猫砂盆、猫厕所</nav><h1>宠物用品 / 猫砂盆、猫厕所</h1><div class="goodsCategory">宠物用品 / 猫用品 / 猫砂盆、猫厕所</div>'
    data = evaluate(html, DETAIL_CATEGORY_JS)
    assert data['paths'] == ['宠物用品 / 猫用品 / 猫砂盆、猫厕所']
