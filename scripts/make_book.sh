#!/bin/bash

# 合并markdown文件
awk 'FNR==1 && NR>1 {print "\n\n---\n"} {print}' /home/wangmaobin/code/Jarvis/docs/jarvis_book/*.md > /tmp/combined_book.md
# 统一将连续换行后紧跟标题的情况替换为两个换行，形如 "\n+^#" -> "\n\n#"
perl -0777 -i -pe 's/\n+(?=^#)/\n\n/mg' /tmp/combined_book.md

# 调用build_pdf.sh生成PDF，并指定输出文件名为当前目录下的Jarvis_Book.pdf
/home/wangmaobin/code/Jarvis/scripts/build_pdf.sh /tmp/combined_book.md ./Jarvis_Book.pdf
