from app.collectors.bunjang import collect_bunjang_kr
from app.collectors.bunjang_global import collect_bunjang_global
from app.collectors.cn_sites import collect_dewu, collect_jd, collect_taobao, collect_zhuanzhuan
from app.collectors.ebay import collect_ebay_au, collect_ebay_us
from app.collectors.karrot import collect_karrot
from app.collectors.xianyu import collect_xianyu

COLLECTORS = [
    collect_ebay_au,
    collect_ebay_us,
    collect_bunjang_kr,
    collect_bunjang_global,
    collect_karrot,
    collect_xianyu,
    collect_taobao,
    collect_dewu,
    collect_zhuanzhuan,
    collect_jd,
]
