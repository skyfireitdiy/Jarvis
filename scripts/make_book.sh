#!/bin/bash

# 合并markdown文件
awk 'FNR==1 && NR>1 {print "\n\n---\n"} {print}' /home/wangmaobin/code/Jarvis/docs/jarvis_book/*.md > /tmp/combined_book.md
# 统一将连续换行后紧跟标题的情况替换为两个换行，形如 "\n+^#" -> "\n\n#"
perl -0777 -i -pe 's/\n+(?=^#)/\n\n/mg' /tmp/combined_book.md
# 在以冒号/全角冒号结尾的说明行后，若下一行是列表项，则补充一个空行，确保列表正确渲染
perl -0777 -i -pe 's/(?m)(^.*[：:][ \t\*\`_~]*\n)(?=(?:[ \t]*(?:[-*+]|\d+\.)\s))/$1\n/g' /tmp/combined_book.md
# 通用规则：任意普通段落后紧跟列表项时，自动补充空行，提升渲染兼容性（不影响标题/代码块/表格/已有列表/分隔线）
perl -0777 -i -pe 's/(?m)(^(?![ \t]*(?:[#>`]|\||(?:[-*+]|\d+\.)\s|-{3,}\s*$)).+\n)(?=(?:[ \t]*(?:[-*+]|\d+\.)\s))/$1\n/g' /tmp/combined_book.md

# 调用build_pdf.sh生成PDF，并指定输出文件名为当前目录下的Jarvis_Book.pdf
/home/wangmaobin/code/Jarvis/scripts/build_pdf.sh /tmp/combined_book.md ./Jarvis_Book.pdf
