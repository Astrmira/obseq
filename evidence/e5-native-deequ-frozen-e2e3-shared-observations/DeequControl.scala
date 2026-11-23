import org.apache.spark.sql.{Row,SparkSession}
import org.apache.spark.sql.types._
import com.amazon.deequ.VerificationSuite
import com.amazon.deequ.checks.{Check,CheckLevel,CheckStatus}
import scala.jdk.CollectionConverters._

object DeequControl {
 def main(args:Array[String]):Unit={
  val s=SparkSession.builder().getOrCreate()
  s.sparkContext.setLogLevel("ERROR")
  try {
   val js=s.read.json(args(0)).orderBy("id").collect()
   val schema=StructType(Seq(StructField("typed_row",StringType,false)))
   js.foreach { r =>
    val id=r.getAs[Long]("id")
    val gold=r.getSeq[String](r.fieldIndex("gold"))
    val rows=r.getSeq[String](r.fieldIndex("candidate"))
    val df=s.createDataFrame(rows.map(x=>Row(x)).asJava,schema)
    val size=Check(CheckLevel.Error,"Stock size against fixed reference").hasSize(_ == gold.size.toLong)
    val pr=gold.groupMapReduce(x=>x)(_=>1)(_+_).toSeq.sortBy(_._1).foldLeft(Check(CheckLevel.Error,"Authored exact typed golden multiset")) {
     case (c,(x,n)) => c.satisfies(s"typed_row = '${x}'",s"frequency ${x}", v=> math.abs(v-n.toDouble/gold.size)<1e-12)
    }
    val suite=VerificationSuite().onData(df)
    val result=if(gold.nonEmpty && rows.nonEmpty) suite.addChecks(Seq(size,pr)).run() else suite.addCheck(size).run()
    def pass(c:Check):Boolean = result.checkResults(c).status==CheckStatus.Success
    val g=if(gold.isEmpty || rows.isEmpty) pass(size) else pass(size)&&pass(pr)
    println("EAB_DECISION\t"+Seq(id,pass(size),g).mkString("\t"))
   }
   println("EAB_SPARK\t"+s.version)
  } finally s.stop()
 }
}
