from pathlib import Path

root = Path("outputs")
atlas = Path("lookup_atlas.json").read_text(encoding="utf-8").replace("</", "<\\/")
html = """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Stickleback · Vector lookup review</title>
<style>
body{font:16px system-ui;margin:2rem auto;padding:0 1rem;max-width:960px;color:#142b3e;background:#f6f8fa}
h1{margin-bottom:.25em} p{line-height:1.45} select,button{font:inherit;padding:.5rem;max-width:100%}
svg{width:min(100%,720px);height:auto;background:#fff;border:1px solid #bac9d6;display:block}
.legend{display:flex;flex-wrap:wrap;gap:1em;font-size:.88rem;margin:1em 0}
</style>
<h1>Stickleback · Vector lookup review</h1>
<p>Inspect the original point, search bounds, and cached water evidence. Choose a site to see its vector map. North is up. Dashed lines are the ArcGIS query box. Thicker colored lines show the selected candidates.</p>
<label for="sites">Study site</label> <select id="sites"></select>
<button id="save">Save this map as SVG</button>
<p id="status"></p><div class="legend" id="legend"></div>
<svg id="map" viewBox="0 0 800 800" width="800" height="800" xmlns="http://www.w3.org/2000/svg" role="img" aria-label="Vector lookup map"></svg>
<p>OSM contributors, ODbL. Cached OSM via Esri and local extracts, frozen HydroRIVERS and lake evidence. Vectors are clipped and simplified for display.</p>
<script>
const sites=__DATA__;
const colors={channel:'#007ca6', coast:'#9466c7',wetland:'#52802d',river_polygon:'#007b71',inland_water:'#c57608',coastal_water:'#3a6ac9'};
const selector=document.querySelector('#sites'), map=document.querySelector('#map');
for(const [id,s] of Object.entries(sites)) selector.add(new Option(id+' · '+s.name,id));
document.querySelector('#legend').innerHTML=Object.entries(colors).map(([k,v])=>'<span style="color:'+v+'">━ '+k.replaceAll('_',' ')+'</span>').join('')+'<span style="color:#d82b60">● Original point</span>';
function render(){
  const id=selector.value,s=sites[id], [w,b,e,n]=s.extent;
  const point=([x,y])=>[42+716*(x-w)/(e-w),758-716*(y-b)/(n-b)];
  const points=line=>line.map(p=>point(p).map(v=>v.toFixed(2)).join(',')).join(' ');
  let svg='<rect width="800" height="800" fill="#fff"/><rect x="42" y="42" width="716" height="716" fill="#f6f9fb" stroke="#e0e7ee"/>';
  if(s.query){
    const [l,d,r,t]=s.query;
    svg+='<polyline points="'+points([[l,d],[r,d],[r,t],[l,t],[l,d]])+'" fill="none" stroke="#263a4e" stroke-width="2" stroke-dasharray="8 5"/>';
  }
  for(const [kind,picked,lines] of [...s.paths].sort((a,b)=>Number(a[1])-Number(b[1]))) {
    for(const line of lines) svg+='<polyline points="'+points(line)+'" fill="none" stroke="'+colors[kind]+'" stroke-width="'+(picked?4:1.3)+'" opacity="'+(picked?1:.55)+'"/>';
  }
  const [x,y]=point(s.point);
  svg+='<circle cx="'+x+'" cy="'+y+'" r="7" fill="#d82b60" stroke="white" stroke-width="2"/>';
  svg+='<text x="42" y="27" font-family="system-ui" font-size="17" fill="#142b3e">'+id+' · 3 km view · north up</text><text x="42" y="785" font-family="system-ui" font-size="13" fill="#142b3e">© OpenStreetMap contributors · ODbL</text>';
  map.innerHTML=svg;
  document.querySelector('#status').textContent=s.habitat+' · '+s.status.replaceAll('_',' ')+' · '+s.paths.length+' displayed vectors'+(s.query?'':' · no ArcGIS query');
}
selector.value='S0419'; selector.onchange=render; render();
document.querySelector('#save').onclick=()=>{const a=document.createElement('a');a.download=selector.value+'_lookup.svg';
 const url=URL.createObjectURL(new Blob([map.outerHTML],{type:'image/svg+xml'}));a.href=url;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
</script></html>"""
(root / "stickleback_vector_review.html").write_text(html.replace("__DATA__", atlas), encoding="utf-8")
