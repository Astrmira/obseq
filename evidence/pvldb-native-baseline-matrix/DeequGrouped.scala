import com.amazon.deequ.VerificationSuite
import com.amazon.deequ.checks.{Check, CheckLevel, CheckStatus}
import org.apache.spark.sql.{Row, SparkSession}
import org.apache.spark.sql.functions.col
import org.apache.spark.sql.types.{StringType, StructField, StructType}
import scala.jdk.CollectionConverters._

object DeequControl {
  def main(args: Array[String]): Unit = {
    val spark = SparkSession.builder().getOrCreate()
    spark.sparkContext.setLogLevel("ERROR")
    try {
      val schema = StructType(Seq(StructField("typed_row", StringType, false)))
      def frame(values: scala.collection.Seq[String]) =
        spark.createDataFrame(values.map(v => Row(v)).asJava, schema)
      spark.read.json(args(0)).orderBy("id").collect().foreach { record =>
        val id = record.getAs[Long]("id")
        val gold = record.getSeq[String](record.fieldIndex("gold"))
        val candidate = frame(record.getSeq[String](record.fieldIndex("candidate")))
        val size = Check(CheckLevel.Error, "Stock size against fixed reference").hasSize(_ == gold.size.toLong)
        val sizeResult = VerificationSuite().onData(candidate).addCheck(size).run()
        val sizePass = sizeResult.checkResults(size).status == CheckStatus.Success
        val goldenPass = if (!sizePass) {
          false
        } else {
          val expected = frame(gold).groupBy("typed_row").count().withColumnRenamed("count", "expected")
          val actual = candidate.groupBy("typed_row").count().withColumnRenamed("count", "actual")
          val mismatches = expected.join(actual, Seq("typed_row"), "full_outer")
            .where(!col("expected").eqNullSafe(col("actual")))
          val check = Check(CheckLevel.Error, "Exact typed multiplicities").hasSize(_ == 0)
          val result = VerificationSuite().onData(mismatches).addCheck(check).run()
          result.checkResults(check).status == CheckStatus.Success
        }
        println(s"EAB_DECISION\t$id\t$sizePass\t$goldenPass")
      }
      println(s"EAB_SPARK\t${spark.version}")
    } finally spark.stop()
  }
}
