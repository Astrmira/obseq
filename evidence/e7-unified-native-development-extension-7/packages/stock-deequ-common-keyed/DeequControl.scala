import org.apache.spark.sql.{DataFrame, Row, SparkSession}
import org.apache.spark.sql.types._
import com.amazon.deequ.VerificationSuite
import com.amazon.deequ.checks.{Check, CheckLevel, CheckStatus}
import com.amazon.deequ.suggestions.{ConstraintSuggestionRunner, Rules}
import java.nio.file.{Files,Paths}
import scala.jdk.CollectionConverters._

object DeequControl {
 def main(args:Array[String]): Unit = {
  val s=SparkSession.builder().getOrCreate()
  s.sparkContext.setLogLevel("ERROR")
  try {
   val schema=StructType(Seq(StructField("id",LongType,true),StructField("g",StringType,true),StructField("v",LongType,true)))
   val json=s.read.json(args(0)).orderBy("id").collect()
   def frame(rows:Seq[Row])=s.createDataFrame(rows.asJava,schema)
   def read(r:Row,k:String)=r.getSeq[Row](r.fieldIndex(k)).map(x=>Row(x.getAs[Long]("_1"),x.getAs[String]("_2"),x.getAs[java.lang.Long]("_3")))
   val ordered=json.map(r=>(r.getAs[String]("id"),read(r,"gold"),read(r,"candidate")))
   val nonempty=ordered.find(_._2.nonEmpty).get
   val training=frame(nonempty._2)
   val suggestions=ConstraintSuggestionRunner().onData(training).addConstraintRules(Rules.DEFAULT).run().constraintSuggestions.values.flatten.toSeq.sortBy(_.codeForConstraint)
   require(suggestions.nonEmpty)
   suggestions.foreach(a=>println("EAB_SUGGEST\t"+a.codeForConstraint))
   val suggested=Check(CheckLevel.Error,"stock suggestions from first nonempty reference",suggestions.map(_.constraint))
   val key=Check(CheckLevel.Error,"id constraints").isComplete("id").isUnique("id")
   val fit=VerificationSuite().onData(training).addCheck(suggested).run()
   println("EAB_FIT\t"+nonempty._1+"\t"+(fit.checkResults(suggested).status==CheckStatus.Success))
   fit.checkResults(suggested).constraintResults.zip(suggestions).foreach { case (r,s) => println("EAB_FIT_RULE\t"+r.status.toString+"\t"+s.codeForConstraint) }
   ordered.foreach { case (id,gold,rows) =>
    val count=Check(CheckLevel.Error,"row count").hasSize(_==gold.size.toLong)
    val r=VerificationSuite().onData(frame(rows)).addChecks(Seq(key,count,suggested)).run()
    def pass(c:Check)=r.checkResults(c).status==CheckStatus.Success
    println("EAB_DECISION\t"+Seq(id,pass(key),pass(key)&&pass(count),pass(suggested)).mkString("\t"))
   }
   println("EAB_SPARK\t"+s.version)
  } finally s.stop()
 }
}
