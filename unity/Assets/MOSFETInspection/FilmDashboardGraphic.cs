using UnityEngine;
using UnityEngine.UI;

[ExecuteAlways,RequireComponent(typeof(CanvasRenderer))]
public class FilmDashboardGraphic : MaskableGraphic
{
    public FilmInspectionDashboard owner;
    public bool wafer;
    [System.NonSerialized] public int drawnVertices;
    void Quad(VertexHelper vh,Vector2 a,Vector2 b,Vector2 c,Vector2 d,Color32 color)
    {int n=vh.currentVertCount;vh.AddVert(a,color,Vector2.zero);vh.AddVert(b,color,Vector2.zero);vh.AddVert(c,color,Vector2.zero);vh.AddVert(d,color,Vector2.zero);vh.AddTriangle(n,n+1,n+2);vh.AddTriangle(n,n+2,n+3);}
    void Line(VertexHelper vh,Vector2 a,Vector2 b,float width,Color32 color)
    {var v=(b-a).normalized;var p=new Vector2(-v.y,v.x)*width/2;Quad(vh,a-p,a+p,b+p,b-p,color);}
    void Disc(VertexHelper vh,Vector2 p,float radius,Color32 color)
    {int n=vh.currentVertCount;vh.AddVert(p,color,Vector2.zero);for(int i=0;i<=64;i++){float a=i*Mathf.PI/32;vh.AddVert(p+new Vector2(Mathf.Cos(a),Mathf.Sin(a))*radius,color,Vector2.zero);if(i>0)vh.AddTriangle(n,n+i+1,n+i);}}
    protected override void OnPopulateMesh(VertexHelper vh)
    {
        vh.Clear();if(!owner||!owner.cycle||!owner.cycle.recipe)return;var c=owner.cycle;var r=rectTransform.rect;var recipe=c.recipe;
        var neutral=new Color32(153,166,158,255);Color32 good=FilmInspectionDashboard.Green,bad=FilmInspectionDashboard.Red;
        if(wafer)
        {
            var centre=r.center;float rad=r.height*.47f;Disc(vh,centre,rad,neutral);Disc(vh,centre,rad-1.4f,new Color32(246,248,242,255));
            Line(vh,centre-Vector2.right*rad,centre+Vector2.right*rad,1,neutral);Line(vh,centre-Vector2.up*rad,centre+Vector2.up*rad,1,neutral);
            Line(vh,centre+new Vector2(-10,-rad),centre+new Vector2(0,-rad+9),2,neutral);Line(vh,centre+new Vector2(0,-rad+9),centre+new Vector2(10,-rad),2,neutral);
            for(int i=0;i<3;i++){float v=c.readings[i];var color=FilmInspectionRecipe.Finite(v)?recipe.InRange(v)?good:bad:c.activePoint==i?new Color32(102,197,255,255):neutral;Disc(vh,centre+Vector2.right*((i-1)*rad*.62f),8,color);}
        }
        else
        {
            float lo=recipe.lowerNm,hi=recipe.upperNm;
            foreach(var value in c.readings)if(FilmInspectionRecipe.Finite(value)){lo=Mathf.Min(lo,value);hi=Mathf.Max(hi,value);}
            float pad=Mathf.Max((hi-lo)*.15f,.1f);lo-=pad;hi+=pad;
            float Y(float v)=>r.yMin+8+(v-lo)/(hi-lo)*(r.height-16);
            Quad(vh,new Vector2(r.xMin,Y(recipe.lowerNm)),new Vector2(r.xMin,Y(recipe.upperNm)),new Vector2(r.xMax,Y(recipe.upperNm)),new Vector2(r.xMax,Y(recipe.lowerNm)),new Color32(227,238,223,255));
            foreach(float v in new[]{recipe.lowerNm,recipe.targetNm,recipe.upperNm})Line(vh,new Vector2(r.xMin,Y(v)),new Vector2(r.xMax,Y(v)),1,neutral);
            Vector2 last=Vector2.zero;bool previous=false;
            for(int i=0;i<3;i++)
            {
                if(!FilmInspectionRecipe.Finite(c.readings[i])){previous=false;continue;}
                var p=new Vector2(r.xMin+r.width*(.1f+i*.4f),Y(c.readings[i]));var color=recipe.InRange(c.readings[i])?good:bad;
                if(previous)Line(vh,last,p,3,color);Disc(vh,p,5,color);last=p;previous=true;
            }
        }
        drawnVertices=vh.currentVertCount;
    }
}

