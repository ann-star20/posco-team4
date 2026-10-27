import pathlib,re
root=pathlib.Path(__file__).resolve().parents[1]
source=root/'Assets/MOSFETInspection/Scenes/MOSFETSmallFab_FacingAisle.unity'
output=source.with_name('MOSFETSmallFab_WideAisle.unity')
text=source.read_text(encoding='utf-8-sig')
blocks=re.split(r'(?m)(?=^--- !u!)',text)
moved=[];transforms={}
for b in blocks:
 if '\nGameObject:\n' in b and re.search(r'm_Name: (Central_Aisle_Edge|Inspection_Zone_Edge)\n',b):
  name=re.search(r'm_Name: (\w+)',b).group(1)
  fid=re.search(r'- component: \{fileID: (\d+)\}',b).group(1)
  transforms[fid]=name
for i,b in enumerate(blocks):
 match=re.search(r'value: (Molding_Machine|AOI_Inspection_Line)\n',b)
 if match:
  def change(m):return m.group(1)+str(float(m.group(2))-1.0)
  b,count=re.subn(r'(propertyPath: m_LocalPosition.z\n\s+value: )([-\d.eE]+)',change,b)
  assert count==1,(match.group(1),count)
  moved.append(match.group(1))
 tid=re.match(r'--- !u!4 &(\d+)\n',b)
 if tid and tid.group(1) in transforms:
  name=transforms[tid.group(1)]
  def stripe(m):
   old=float(m.group(2));new=old-1 if name=='Inspection_Zone_Edge' or old<-1 else old
   return m.group(1)+str(new)+m.group(3)
  b,count=re.subn(r'(m_LocalPosition: \{x: [^,]+, y: [^,]+, z: )([-\d.eE]+)(\})',stripe,b)
  assert count==1
 blocks[i]=b
assert sorted(moved)==['AOI_Inspection_Line','Molding_Machine'],moved
output.write_text(''.join(blocks),encoding='utf-8')
print('SAVED',output,'equipment moved -1m:',moved,'aisle 2.5m')
