/* Safe Markdown for model replies (Chat V2). Original NajdiLab implementation.
 * The stored reply is never changed: this only builds display nodes.
 * Safety: text becomes DOM text nodes; HTML in a reply is shown as text; no
 * HTML string is ever parsed; links are kept only for http(s) and mailto URLs. */
(function(global){
  'use strict';
  const MAX_INPUT=262144, MAX_DEPTH=4, SAFE_PROTOCOLS=new Set(['http:','https:','mailto:']);
  const FENCE=/^\s{0,3}(`{3,}|~{3,})\s*([\w+#.-]{0,32})\s*$/;
  const HEADING=/^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
  const RULE=/^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/;
  const QUOTE=/^\s{0,3}>\s?(.*)$/;
  const ITEM=/^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  const TABLE_SEP=/^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;

  function safeHref(raw){
    if(typeof raw!=='string')return null;
    const value=raw.trim();
    if(!value||/[\u0000-\u001f\s]/.test(value))return null;
    let url;
    try{url=new URL(value);}catch{return null;} // relative or malformed: shown as text
    return SAFE_PROTOCOLS.has(url.protocol)?url.href:null;
  }

  // ---------------------------------------------------------------- inline
  function inline(text,depth=0){
    const out=[];let buffer='';
    const flush=()=>{if(buffer){out.push({type:'text',text:buffer});buffer='';}};
    let i=0;
    while(i<text.length){
      const rest=text.slice(i),ch=text[i];
      // Escapes are never decoded (ported from PR #21, 95e7604): the backslash and
      // the whole delimiter run it escapes stay visible as literal source text.
      if(ch==='\\'&&i+1<text.length&&/[\\`*_{}\[\]()#+\-.!~|>]/.test(text[i+1])){
        const run=rest.slice(1).match(/^([`*_~])\1*/);
        const width=1+(run?run[0].length:1);buffer+=text.slice(i,i+width);i+=width;continue;
      }
      if(ch==='`'){
        const ticks=rest.match(/^`+/)[0],end=text.indexOf(ticks,i+ticks.length);
        if(end>i){flush();out.push({type:'code',text:text.slice(i+ticks.length,end).replace(/^ (.*) $/,'$1')});i=end+ticks.length;continue;}
      }
      if(depth<MAX_DEPTH){
        // A closing delimiter preceded by an odd number of backslashes is escaped.
        const escapedEnd=content=>/(^|[^\\])(\\\\)*\\$/.test(content);
        let m=rest.match(/^(\*\*|__)(?=\S)([\s\S]*?\S)\1/);
        if(m&&!escapedEnd(m[2])&&!(m[1]==='__'&&/\w/.test(text[i-1]||''))){flush();out.push({type:'strong',children:inline(m[2],depth+1)});i+=m[0].length;continue;}
        m=rest.match(/^~~(?=\S)([\s\S]*?\S)~~/);
        if(m&&!escapedEnd(m[1])){flush();out.push({type:'del',children:inline(m[1],depth+1)});i+=m[0].length;continue;}
        m=rest.match(/^(\*(?!\*)|_(?!_))(?=\S)([\s\S]*?\S)\1(?!\1)/);
        if(m&&!escapedEnd(m[2])&&!(m[1]==='_'&&(/\w/.test(text[i-1]||'')||/\w/.test(text[i+m[0].length]||'')))){flush();out.push({type:'em',children:inline(m[2],depth+1)});i+=m[0].length;continue;}
        m=rest.match(/^\[([^\]\n]{1,500})\]\(\s*<?([^\s)<>]{1,2048})>?(?:\s+"[^"\n]{0,200}")?\s*\)/);
        if(m){
          flush();const href=safeHref(m[2]);
          out.push(href?{type:'link',href,children:inline(m[1],depth+1)}:{type:'text',text:m[0]});
          i+=m[0].length;continue;
        }
      }
      let m=rest.match(/^<(https?:\/\/[^\s<>]{1,2048})>/);
      if(m&&safeHref(m[1])){flush();out.push({type:'link',href:safeHref(m[1]),children:[{type:'text',text:m[1]}]});i+=m[0].length;continue;}
      m=/^https?:\/\/[^\s<>()]{1,2048}/.exec(rest);
      if(m&&!/\w/.test(text[i-1]||'')){
        const url=m[0].replace(/[.,;:!?،؛]+$/,'');const href=safeHref(url);
        if(href){flush();out.push({type:'link',href,children:[{type:'text',text:url}]});i+=url.length;continue;}
      }
      if(ch==='\n'){flush();out.push({type:'br'});i++;continue;}
      buffer+=ch;i++;
    }
    flush();return out;
  }

  // ---------------------------------------------------------------- blocks
  function cells(line){
    let body=line.trim();if(body.startsWith('|'))body=body.slice(1);if(body.endsWith('|')&&!body.endsWith('\\|'))body=body.slice(0,-1);
    return body.split(/(?<!\\)\|/).map(cell=>cell.trim().replace(/\\\|/g,'|'));
  }

  function blocks(lines,depth=0){
    const out=[];let i=0;
    while(i<lines.length){
      const line=lines[i];
      if(!line.trim()){i++;continue;}
      let m=line.match(FENCE);
      if(m){
        const fence=m[1],body=[];i++;
        while(i<lines.length&&!(lines[i].trim().startsWith(fence[0].repeat(fence.length))&&!lines[i].trim().replace(new RegExp('^\\'+fence[0]+'+'),'').trim()))body.push(lines[i++]);
        const closed=i<lines.length;if(closed)i++;
        out.push({type:'code',lang:m[2]||'',text:body.join('\n'),closed});continue;
      }
      if((m=line.match(HEADING))){out.push({type:'heading',level:m[1].length,children:inline(m[2])});i++;continue;}
      if(RULE.test(line)){out.push({type:'rule'});i++;continue;}
      if(QUOTE.test(line)&&depth<MAX_DEPTH){
        const inner=[];while(i<lines.length&&QUOTE.test(lines[i]))inner.push(lines[i++].match(QUOTE)[1]);
        out.push({type:'quote',children:blocks(inner,depth+1)});continue;
      }
      if(line.includes('|')&&i+1<lines.length&&TABLE_SEP.test(lines[i+1])&&lines[i+1].includes('-')){
        const head=cells(line),rows=[];i+=2;
        while(i<lines.length&&lines[i].trim()&&lines[i].includes('|'))rows.push(cells(lines[i++]));
        out.push({type:'table',head:head.map(c=>inline(c)),rows:rows.map(r=>head.map((_,k)=>inline(r[k]||'')))});continue;
      }
      if((m=line.match(ITEM))&&depth<MAX_DEPTH){
        const indent=m[1].length,ordered=/\d/.test(m[2]),items=[];
        const start=ordered?parseInt(m[2],10):null;
        while(i<lines.length){
          const im=lines[i].match(ITEM);
          if(im&&im[1].length===indent&&/\d/.test(im[2])===ordered){items.push([im[3]]);i++;continue;}
          if(lines[i].trim()&&(lines[i].match(/^\s*/)[0].length>indent||(!ITEM.test(lines[i])&&items.length&&lines[i-1].trim()))){
            items[items.length-1].push(lines[i].slice(Math.min(indent+2,lines[i].match(/^\s*/)[0].length)));i++;continue;
          }
          break;
        }
        out.push({type:'list',ordered,start,items:items.map(body=>{
          const nested=body.findIndex((l,k)=>k>0&&ITEM.test(l));
          const lead=(nested<0?body:body.slice(0,nested)).join('\n');
          return {children:inline(lead),blocks:nested<0?[]:blocks(body.slice(nested),depth+1)};
        })});continue;
      }
      const para=[];
      const tableStart=k=>lines[k].includes('|')&&k+1<lines.length&&TABLE_SEP.test(lines[k+1])&&lines[k+1].includes('-');
      while(i<lines.length&&lines[i].trim()&&!FENCE.test(lines[i])&&!HEADING.test(lines[i])&&!RULE.test(lines[i])&&!QUOTE.test(lines[i])&&!(para.length&&(ITEM.test(lines[i])||tableStart(i))))para.push(lines[i++]);
      if(!para.length)para.push(lines[i++]);
      out.push({type:'paragraph',children:inline(para.join('\n'))});
    }
    return out;
  }

  function parse(text){
    const source=String(text??'');
    if(source.length>MAX_INPUT)return [{type:'paragraph',children:[{type:'text',text:source}]}];
    return blocks(source.replace(/\r\n?/g,'\n').split('\n'));
  }

  // ---------------------------------------------------------------- DOM
  function build(nodes,doc,options={}){
    const fragment=doc.createDocumentFragment();
    const t=options.t||(s=>s);
    const add=(parent,list)=>{for(const node of list)parent.append(make(node));return parent;};
    function el(tag,cls){const e=doc.createElement(tag);if(cls)e.className=cls;return e;}
    function make(node){
      switch(node.type){
        case 'text':return doc.createTextNode(node.text);
        case 'br':return el('br');
        case 'code':{
          if(node.lang!==undefined&&'closed' in node)return codeBlock(node);
          const c=el('code','md-inline-code');c.textContent=node.text;c.dir='auto';return c;
        }
        case 'strong':return add(el('strong'),node.children);
        case 'em':return add(el('em'),node.children);
        case 'del':return add(el('del'),node.children);
        case 'link':{const a=el('a');a.href=node.href;a.rel='noopener noreferrer nofollow';a.target='_blank';a.dir='auto';return add(a,node.children);}
        case 'heading':{const h=el('h'+Math.min(6,node.level+2),'md-heading');h.dir='auto';return add(h,node.children);}
        case 'rule':return el('hr');
        case 'quote':{const q=el('blockquote');q.dir='auto';q.append(build(node.children,doc,options));return q;}
        case 'paragraph':{const p=el('p');p.dir='auto';return add(p,node.children);}
        case 'list':{
          const list=el(node.ordered?'ol':'ul');list.dir='auto';
          if(node.ordered&&node.start&&node.start!==1)list.start=node.start;
          for(const item of node.items){const li=el('li');add(li,item.children);if(item.blocks.length)li.append(build(item.blocks,doc,options));list.append(li);}
          return list;
        }
        case 'table':{
          const wrap=el('div','md-table'),table=el('table'),thead=el('thead'),tbody=el('tbody'),hr=el('tr');
          table.dir='auto';
          for(const cell of node.head)hr.append(add(el('th'),cell));
          thead.append(hr);
          for(const row of node.rows){const tr=el('tr');for(const cell of row)tr.append(add(el('td'),cell));tbody.append(tr);}
          table.append(thead,tbody);wrap.append(table);return wrap;
        }
        default:return doc.createTextNode('');
      }
    }
    function codeBlock(node){
      const box=el('div','md-code'),head=el('div','md-code-head'),label=el('span','md-code-lang'),copy=el('button','md-copy');
      label.textContent=node.lang||t('Code');label.setAttribute('translate','no');
      copy.type='button';copy.textContent=t('Copy code');copy.dataset.code=node.text;
      // Focusable so a wide block can be scrolled with the keyboard (WCAG 2.1.1).
      const pre=el('pre'),code=el('code');pre.dir='ltr';pre.tabIndex=0;pre.setAttribute('aria-label',t('Code'));code.textContent=node.text;pre.append(code);
      head.append(label,copy);box.append(head,pre);return box;
    }
    for(const node of nodes)fragment.append(make(node));
    return fragment;
  }

  function render(text,doc,options){return build(parse(text),doc||global.document,options);}

  const api={parse,inline,render,build,safeHref};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;
  else global.NajdiMarkdown=api;
})(typeof window!=='undefined'?window:globalThis);
