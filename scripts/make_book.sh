#!/bin/bash

# 合并markdown文件
awk 'FNR==1 && NR>1 {print "\n\n---\n"} {print}' /home/wangmaobin/code/Jarvis/docs/jarvis_book/*.md > /tmp/combined_book.md
# 统一将连续换行后紧跟标题的情况替换为两个换行，形如 "\n+^#" -> "\n\n#"
perl -0777 -i -pe 's/\n+(?=^#)/\n\n/mg' /tmp/combined_book.md
# 仅在代码块外执行列表空行修正规则，避免影响代码中的行首 '-' 或数字列表
perl -0777 -i -pe '
  my $text = $_;
  my $out = "";
  my $last = 0;

  # 按段处理：遇到围栏代码块（``` 或 ~~~）则原样保留，其余文本段应用列表空行修正规则
  while ($text =~ /(.*?)(^[ \t]*([`~]{3,}).*?\n.*?^\s*\3[ \t]*\s*$)/gms) {
    my ($pre, $code) = ($1, $2);

    # 规则1：以冒号/全角冒号结尾的说明行后若紧跟列表项，则补充空行
    $pre =~ s/(?m)(^.*[：:][ \t\*\`_~]*\n)(?=(?:[ \t]*(?:[-*+]|\d+[.)）])\s))/$1\n/g;

    # 规则2：普通段落后紧跟列表项时，补充空行（排除标题/引用/代码围栏/表格/已有列表/分隔线）
    $pre =~ s/(?m)(^(?![ \t]*(?:[#>`]|\||(?:[-*+]|\d+[.)）])\s|-{3,}\s*$)).+\n)(?=(?:[ \t]*(?:[-*+]|\d+[.)）])\s))/$1\n/g;

    $out .= $pre . $code;
    $last = pos($text);
  }

  # 处理最后一段（不在代码块中的尾部文本）
  my $tail = substr($text, $last);
  $tail =~ s/(?m)(^.*[：:][ \t\*\`_~]*\n)(?=(?:[ \t]*(?:[-*+]|\d+[.)）])\s))/$1\n/g;
  $tail =~ s/(?m)(^(?![ \t]*(?:[#>`]|\||(?:[-*+]|\d+[.)）])\s|-{3,}\s*$)).+\n)(?=(?:[ \t]*(?:[-*+]|\d+[.)）])\s))/$1\n/g;

  $_ = $out . $tail;
' /tmp/combined_book.md
# 在表格表头前增加一个空行（仅在表头行之前，匹配下一行为分隔线的情况）
perl -0777 -i -pe 's/(?m)(^.+\S.*\n)(?=(?:[ \t]*\|.*\|\s*\n[ \t]*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$))/$1\n/g' /tmp/combined_book.md

# 调用build_pdf.sh生成PDF，并指定输出文件名为当前目录下的Jarvis_Book.pdf
/home/wangmaobin/code/Jarvis/scripts/build_pdf.sh /tmp/combined_book.md ./Jarvis_Book.pdf
